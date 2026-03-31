from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set

from app.utils.logger import get_logger

logger = get_logger("agentv3_event_hub")


class AgentV3EventHub:
    def __init__(self, history_limit: int = 2000):
        self.subscribers: Set[Any] = set()
        self.event_seq_by_session: Dict[str, int] = {}
        self.event_id_counter: int = 0
        self.event_history: List[Dict[str, Any]] = []
        self.event_history_limit = history_limit
        self._transport_events = {"server.connected", "server.heartbeat"}

    async def subscribe_events(
        self,
        *,
        lock: asyncio.Lock,
        stream_heartbeat_ms: int,
        last_event_id: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        connected_event = await self.stamp_event(
            {
                "type": "server.connected",
                "sessionID": "",
                "messageID": None,
                "engine": "agentv3",
                "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                "properties": {"transport": "sse"},
            },
            lock=lock,
        )
        await queue.put(connected_event)
        if isinstance(last_event_id, int) and last_event_id > 0:
            async with lock:
                replay = [event for event in self.event_history if int(event.get("eventID") or 0) > last_event_id]
            logger.info("agentv3 replay requested last_event_id=%s replay_count=%s", last_event_id, len(replay))
            for event in replay:
                await queue.put(event)
        self.subscribers.add(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=stream_heartbeat_ms / 1000)
                    yield event
                except asyncio.TimeoutError:
                    heartbeat_event = await self.stamp_event(
                        {
                            "type": "server.heartbeat",
                            "sessionID": "",
                            "messageID": None,
                            "engine": "agentv3",
                            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
                            "properties": {"transport": "sse"},
                        },
                        lock=lock,
                    )
                    yield heartbeat_event
        finally:
            self.subscribers.discard(queue)

    async def emit(
        self,
        *,
        event_type: str,
        session_id: str,
        message_id: Optional[str],
        properties: Optional[Dict[str, Any]],
        lock: asyncio.Lock,
        apply_to_store,
    ) -> Dict[str, Any]:
        raw_event = {
            "type": event_type,
            "sessionID": session_id,
            "messageID": message_id,
            "engine": "agentv3",
            "ts": int(datetime.now(timezone.utc).timestamp() * 1000),
            "properties": properties or {},
        }
        event = await self.stamp_event(raw_event, lock=lock)
        await apply_to_store(event)
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(event)
            except Exception as err:  # pragma: no cover
                logger.warning("agentv3 queue put failed: %s", err)
        return event

    async def stamp_event(self, event: Dict[str, Any], *, lock: asyncio.Lock) -> Dict[str, Any]:
        session_id = str(event.get("sessionID") or "")
        event_type = str(event.get("type") or "")
        async with lock:
            next_seq = self.event_seq_by_session.get(session_id, 0) + 1 if session_id else 0
            if session_id:
                self.event_seq_by_session[session_id] = next_seq
            self.event_id_counter += 1
            event_id = self.event_id_counter
        stamped = dict(event)
        stamped.setdefault("engine", "agentv3")
        stamped.setdefault("ts", int(datetime.now(timezone.utc).timestamp() * 1000))
        stamped["eventID"] = event_id
        if session_id:
            stamped["seq"] = next_seq
        if self._is_replayable_event(event_type):
            async with lock:
                self.event_history.append(stamped)
                if len(self.event_history) > self.event_history_limit:
                    self.event_history = self.event_history[-self.event_history_limit :]
        return stamped

    def _is_replayable_event(self, event_type: str) -> bool:
        return event_type not in self._transport_events

    async def apply_event_to_store(
        self,
        event: Dict[str, Any],
        *,
        lock: asyncio.Lock,
        sessions: Dict[str, Dict[str, Any]],
        messages: Dict[str, List[Dict[str, Any]]],
        now_iso,
    ) -> None:
        event_type = str(event.get("type") or "")
        session_id = str(event.get("sessionID") or "")
        message_id = str(event.get("messageID") or "")
        properties = event.get("properties") or {}
        async with lock:
            if not session_id or session_id not in sessions:
                return
            if event_type == "session.status":
                status_raw = properties.get("status")
                if isinstance(status_raw, dict):
                    status_type = str(status_raw.get("type") or "").strip().lower()
                    sessions[session_id]["status"] = "idle" if status_type == "idle" else "running"
                else:
                    status_text = str(status_raw or "").strip().lower()
                    sessions[session_id]["status"] = "idle" if status_text == "idle" else "running"
                sessions[session_id]["time"]["updated"] = now_iso()
                return
            if event_type in {"session.idle", "session.error"}:
                sessions[session_id]["status"] = "idle"
                sessions[session_id]["time"]["updated"] = now_iso()
                return
            rows = messages.setdefault(session_id, [])
            if event_type == "message.updated":
                info = properties.get("info")
                if isinstance(info, dict) and message_id:
                    idx = self._find_message_index(rows, message_id)
                    if idx >= 0:
                        rows[idx]["info"] = {**rows[idx].get("info", {}), **info}
                    else:
                        rows.append({"info": info, "parts": []})
                return
            if event_type == "message.part.updated":
                part = properties.get("part")
                if not isinstance(part, dict):
                    return
                mid = str(part.get("messageID") or message_id)
                if not mid:
                    return
                idx = self._find_message_index(rows, mid)
                if idx < 0:
                    rows.append({"info": {"id": mid, "role": "assistant", "sessionID": session_id, "time": {}}, "parts": []})
                    idx = len(rows) - 1
                parts = rows[idx].setdefault("parts", [])
                part_idx = self._find_part_index(parts, str(part.get("id") or ""))
                if part_idx >= 0:
                    parts[part_idx] = {**parts[part_idx], **part}
                else:
                    parts.append(part)
                return
            if event_type == "message.part.delta":
                mid = str(properties.get("messageID") or message_id)
                part_id = str(properties.get("partID") or "")
                field = str(properties.get("field") or "text")
                delta = str(properties.get("delta") or "")
                if not mid or not part_id:
                    return
                idx = self._find_message_index(rows, mid)
                if idx < 0:
                    rows.append({"info": {"id": mid, "role": "assistant", "sessionID": session_id, "time": {}}, "parts": []})
                    idx = len(rows) - 1
                parts = rows[idx].setdefault("parts", [])
                part_idx = self._find_part_index(parts, part_id)
                if part_idx < 0:
                    part_type = "reasoning" if str(properties.get("partType") or "") == "reasoning" else "text"
                    parts.append({"id": part_id, "type": part_type, "messageID": mid, field: delta})
                    return
                current = str(parts[part_idx].get(field) or "")
                parts[part_idx][field] = current + delta

    def _find_message_index(self, rows: List[Dict[str, Any]], message_id: str) -> int:
        for idx, row in enumerate(rows):
            if str(row.get("info", {}).get("id") or "") == message_id:
                return idx
        return -1

    def _find_part_index(self, parts: List[Dict[str, Any]], part_id: str) -> int:
        for idx, part in enumerate(parts):
            if str(part.get("id") or "") == part_id:
                return idx
        return -1
