from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Literal, cast
import uuid

from app.utils.logger import get_logger

from .artifact_store import TtsArtifactStore, get_tts_artifact_store
from .synthesis_service import TtsSegment, TtsSynthesisService, get_tts_synthesis_service

TaskStatus = Literal["queued", "running", "completed", "failed", "cancelled"]
logger = get_logger("tts_runtime_service")


@dataclass(slots=True)
class TtsTask:
    task_id: str
    plugin_id: str
    text: str
    voice: str
    sid: int | None
    mode: str
    status: TaskStatus = "queued"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    error_code: str | None = None
    message: str = ""
    total_segments: int = 0
    completed_segments: int = 0
    cancelled: bool = False
    runner: asyncio.Task | None = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "plugin_id": self.plugin_id,
            "status": self.status,
            "sid": self.sid,
            "message": self.message,
            "error_code": self.error_code,
            "total_segments": self.total_segments,
            "completed_segments": self.completed_segments,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class TtsRuntimeService:
    def __init__(
        self,
        synthesis_service: TtsSynthesisService | None = None,
        artifact_store: TtsArtifactStore | None = None,
        event_history_ttl_seconds: int = 180,
        max_terminal_tasks: int = 128,
        watcher_queue_maxsize: int = 64,
        max_watchers_per_task: int = 8,
        max_event_history_per_task: int = 512,
    ) -> None:
        self._synthesis = synthesis_service or get_tts_synthesis_service()
        self._store = artifact_store or get_tts_artifact_store()
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, TtsTask] = {}
        self._active_task_by_plugin: Dict[str, str] = {}
        self._watchers: Dict[str, List[asyncio.Queue[dict[str, Any]]]] = {}
        self._event_history: Dict[str, List[dict[str, Any]]] = {}
        self._event_seq: Dict[str, int] = {}
        self._last_error_by_plugin: Dict[str, str] = {}
        self._event_history_ttl_seconds = max(10, int(event_history_ttl_seconds))
        self._max_terminal_tasks = max(16, int(max_terminal_tasks))
        self._watcher_queue_maxsize = max(8, int(watcher_queue_maxsize))
        self._max_watchers_per_task = max(1, int(max_watchers_per_task))
        self._max_event_history_per_task = max(32, int(max_event_history_per_task))
        self._bridge_observability: Dict[str, Dict[str, Any]] = {}

    async def submit_speak(
        self,
        *,
        plugin_id: str,
        text: str,
        voice: str = "",
        sid: int | None = None,
        mode: str = "manual",
        interrupt: bool = False,
    ) -> str:
        plugin_key = str(plugin_id or "").strip()
        if not plugin_key:
            raise ValueError("plugin_id is required")
        payload = str(text or "").strip()
        if not payload:
            raise ValueError("text is required")
        task_id = str(uuid.uuid4())
        task = TtsTask(
            task_id=task_id,
            plugin_id=plugin_key,
            text=payload,
            voice=str(voice or "").strip(),
            sid=sid,
            mode=str(mode or "manual").strip() or "manual",
        )
        async with self._lock:
            if interrupt:
                await self._cancel_active_task_locked(plugin_key)
            self._tasks[task_id] = task
            self._watchers[task_id] = []
            self._event_history[task_id] = []
            self._event_seq[task_id] = 0
            self._active_task_by_plugin[plugin_key] = task_id
            self._store.register_task(task_id)
            task.runner = asyncio.create_task(self._run_task(task))
        logger.info(
            "tts_task_submitted task_id=%s plugin=%s interrupt=%s sid=%s mode=%s text_len=%s",
            task_id,
            plugin_key,
            interrupt,
            sid,
            task.mode,
            len(payload),
        )
        return task_id

    async def stop(self, *, task_id: str | None = None, plugin_id: str | None = None) -> bool:
        async with self._lock:
            target_task_id = ""
            if task_id:
                target_task_id = str(task_id).strip()
            elif plugin_id:
                target_task_id = self._active_task_by_plugin.get(str(plugin_id).strip(), "")
            if not target_task_id:
                return False
            task = self._tasks.get(target_task_id)
            if task is None:
                return False
            task.cancelled = True
            runner = task.runner
        if runner and not runner.done():
            runner.cancel()
        return True

    def get_task(self, task_id: str) -> Dict[str, Any] | None:
        task = self._tasks.get(str(task_id).strip())
        return task.to_dict() if task else None

    def get_plugin_runtime_state(self, plugin_id: str) -> Dict[str, Any]:
        plugin_key = str(plugin_id or "").strip()
        active_task_id = self._active_task_by_plugin.get(plugin_key) or ""
        active_task = self._tasks.get(active_task_id) if active_task_id else None
        state = "available"
        if active_task and active_task.status in {"queued", "running"}:
            state = "running"
        if self._last_error_by_plugin.get(plugin_key):
            state = "degraded"
        return {
            "state": state,
            "mode": "manual",
            "active_task": active_task.to_dict() if active_task else None,
            "queue_depth": 1 if active_task and active_task.status in {"queued", "running"} else 0,
            "last_error": self._last_error_by_plugin.get(plugin_key, ""),
            "model": self._synthesis.model_descriptor(),
            "bridge": dict(self._bridge_observability.get(plugin_key) or self._new_bridge_observability()),
        }

    async def reset_plugin(self, plugin_id: str) -> None:
        await self.stop(plugin_id=plugin_id)
        plugin_key = str(plugin_id or "").strip()
        self._last_error_by_plugin.pop(plugin_key, None)

    async def ensure_event_cursor(self, task_id: str, last_event_id: int | None) -> None:
        if last_event_id is None or last_event_id <= 0:
            return
        key = str(task_id).strip()
        async with self._lock:
            history = list(self._event_history.get(key, []))
        has_cursor = any(int(item.get("_id") or 0) == last_event_id for item in history)
        if not has_cursor:
            raise ValueError("tts_event_cursor_not_found")

    async def subscribe_events(self, task_id: str, last_event_id: int | None = None):
        key = str(task_id).strip()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._watcher_queue_maxsize)
        async with self._lock:
            if key not in self._watchers:
                self._watchers[key] = []
            history = list(self._event_history.get(key, []))
            if last_event_id is not None and last_event_id > 0:
                has_cursor = any(int(item.get("_id") or 0) == last_event_id for item in history)
                if not has_cursor:
                    raise ValueError("tts_event_cursor_not_found")
            if last_event_id is not None:
                history = [item for item in history if int(item.get("_id") or 0) > last_event_id]
            should_watch = True
            if history:
                last_event = str(history[-1].get("event") or "")
                if last_event in {"done", "error", "cancelled"}:
                    should_watch = False
            if should_watch:
                watchers = self._watchers[key]
                if len(watchers) >= self._max_watchers_per_task:
                    logger.warning(
                        "tts_watchers_limit_reached task_id=%s max_watchers=%s",
                        key,
                        self._max_watchers_per_task,
                    )
                    should_watch = False
                else:
                    watchers.append(queue)
        for event in history:
            yield event
            if event.get("event") in {"done", "error", "cancelled"}:
                return
        if not should_watch:
            return
        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("event") in {"done", "error", "cancelled"}:
                    break
        finally:
            async with self._lock:
                watchers = self._watchers.get(key, [])
                if queue in watchers:
                    watchers.remove(queue)

    async def _run_task(self, task: TtsTask) -> None:
        try:
            task.status = "running"
            task.updated_at = datetime.utcnow()
            logger.info("tts_task_started task_id=%s plugin=%s sid=%s", task.task_id, task.plugin_id, task.sid)
            task.total_segments = len(self._synthesis.split_sentences(task.text))
            await self._publish(
                task.task_id,
                {
                    "event": "progress",
                    "data": {
                        "task_id": task.task_id,
                        "completed_segments": 0,
                        "total_segments": task.total_segments,
                    },
                },
            )
            iterator = iter(self._iter_task_segments(task))
            sentinel = object()
            while True:
                next_segment = await asyncio.to_thread(next, iterator, sentinel)
                if next_segment is sentinel:
                    break
                segment = cast(TtsSegment, next_segment)
                if task.cancelled:
                    raise asyncio.CancelledError()
                self._store.write_segment(task.task_id, segment.seq, segment.wav_bytes)
                task.completed_segments = segment.seq
                task.updated_at = datetime.utcnow()
                await self._publish(
                    task.task_id,
                    {
                        "event": "segment_ready",
                        "data": {
                            "task_id": task.task_id,
                            "plugin_id": task.plugin_id,
                            "seq": segment.seq,
                            "duration_ms": segment.duration_ms,
                            "url": f"/api/tts/audio/{task.task_id}/{segment.seq}.wav",
                        },
                    },
                )
                await self._publish(
                    task.task_id,
                    {
                        "event": "progress",
                        "data": {
                            "task_id": task.task_id,
                            "completed_segments": task.completed_segments,
                            "total_segments": task.total_segments,
                        },
                    },
                )
            task.status = "completed"
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            self._store.mark_completed(task.task_id)
            logger.info(
                "tts_task_completed task_id=%s plugin=%s total_segments=%s",
                task.task_id,
                task.plugin_id,
                task.total_segments,
            )
            await self._publish(
                task.task_id,
                {
                    "event": "done",
                    "data": {
                        "task_id": task.task_id,
                        "total_segments": task.total_segments,
                    },
                },
            )
        except asyncio.CancelledError:
            task.status = "cancelled"
            task.error_code = "TTS_RUNTIME_CANCELLED"
            task.message = "tts task cancelled"
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            logger.info("tts_task_cancelled task_id=%s plugin=%s", task.task_id, task.plugin_id)
            await self._publish(task.task_id, {"event": "cancelled", "data": {"task_id": task.task_id}})
        except Exception as err:
            task.status = "failed"
            task.error_code = self._map_error_code(str(err))
            task.message = str(err)
            task.completed_at = datetime.utcnow()
            task.updated_at = datetime.utcnow()
            self._last_error_by_plugin[task.plugin_id] = str(err)
            logger.warning(
                "tts_task_failed task_id=%s plugin=%s code=%s message=%s",
                task.task_id,
                task.plugin_id,
                task.error_code,
                task.message,
            )
            await self._publish(
                task.task_id,
                {
                    "event": "error",
                    "data": {
                        "task_id": task.task_id,
                        "code": task.error_code,
                        "message": task.message,
                    },
                },
            )
        finally:
            async with self._lock:
                if self._active_task_by_plugin.get(task.plugin_id) == task.task_id:
                    self._active_task_by_plugin.pop(task.plugin_id, None)
                self._prune_task_metadata_locked()
            self._store.cleanup_expired()

    def _iter_task_segments(self, task: TtsTask) -> Iterable[TtsSegment]:
        iter_synthesize = getattr(self._synthesis, "iter_synthesize", None)
        if callable(iter_synthesize):
            handler = cast(Callable[..., Iterable[TtsSegment]], iter_synthesize)
            return handler(text=task.text, voice=task.voice, sid=task.sid)
        return self._synthesis.synthesize(text=task.text, voice=task.voice, sid=task.sid)

    async def _cancel_active_task_locked(self, plugin_id: str) -> None:
        active_task_id = self._active_task_by_plugin.get(plugin_id) or ""
        if not active_task_id:
            return
        task = self._tasks.get(active_task_id)
        if task is None:
            return
        task.cancelled = True
        runner = task.runner
        if runner and not runner.done():
            runner.cancel()

    async def _publish(self, task_id: str, event: dict[str, Any]) -> None:
        async with self._lock:
            seq = int(self._event_seq.get(task_id, 0)) + 1
            self._event_seq[task_id] = seq
            payload = dict(event)
            payload["_id"] = seq
            history = self._event_history.setdefault(task_id, [])
            history.append(payload)
            overflow = len(history) - self._max_event_history_per_task
            if overflow > 0:
                del history[:overflow]
            watchers = list(self._watchers.get(task_id, []))
        overflow_watchers: list[asyncio.Queue[dict[str, Any]]] = []
        for queue in watchers:
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                overflow_watchers.append(queue)
        if overflow_watchers:
            logger.warning(
                "tts_watcher_backpressure task_id=%s dropped_watchers=%s",
                task_id,
                len(overflow_watchers),
            )
            async with self._lock:
                current_watchers = self._watchers.get(task_id, [])
                for queue in overflow_watchers:
                    if queue in current_watchers:
                        current_watchers.remove(queue)

    def _prune_task_metadata_locked(self) -> None:
        now = datetime.utcnow()
        removable: list[str] = []
        for task_id, task in self._tasks.items():
            if task.status not in {"completed", "failed", "cancelled"}:
                continue
            completed_at = task.completed_at or task.updated_at
            if (now - completed_at).total_seconds() < self._event_history_ttl_seconds:
                continue
            watchers = self._watchers.get(task_id, [])
            if watchers:
                continue
            removable.append(task_id)

        for task_id in removable:
            self._drop_task_metadata_locked(task_id)

        terminal_candidates: list[tuple[datetime, str]] = []
        for task_id, task in self._tasks.items():
            if task.status not in {"completed", "failed", "cancelled"}:
                continue
            if self._watchers.get(task_id):
                continue
            terminal_candidates.append((task.completed_at or task.updated_at, task_id))
        if len(terminal_candidates) <= self._max_terminal_tasks:
            return
        terminal_candidates.sort(key=lambda item: item[0])
        overflow = len(terminal_candidates) - self._max_terminal_tasks
        for _, task_id in terminal_candidates[:overflow]:
            self._drop_task_metadata_locked(task_id)

    def _drop_task_metadata_locked(self, task_id: str) -> None:
        self._tasks.pop(task_id, None)
        self._event_history.pop(task_id, None)
        self._event_seq.pop(task_id, None)
        self._watchers.pop(task_id, None)

    async def record_bridge_notify(
        self,
        *,
        plugin_id: str,
        ok: bool,
        error_code: str = "",
    ) -> None:
        plugin_key = str(plugin_id or "").strip()
        if not plugin_key:
            return
        async with self._lock:
            payload = self._bridge_observability.setdefault(plugin_key, self._new_bridge_observability())
            payload["bridge_notify_total"] = int(payload.get("bridge_notify_total", 0)) + 1
            if ok:
                return
            payload["bridge_notify_failures"] = int(payload.get("bridge_notify_failures", 0)) + 1
            payload["last_bridge_error_code"] = str(error_code or "unknown_error")
            payload["last_bridge_error_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def _new_bridge_observability() -> Dict[str, Any]:
        return {
            "bridge_notify_total": 0,
            "bridge_notify_failures": 0,
            "last_bridge_error_code": "",
            "last_bridge_error_at": "",
        }

    @staticmethod
    def _map_error_code(message: str) -> str:
        payload = str(message or "").lower()
        if "init failed" in payload or "model file not found" in payload or "missing sherpa-onnx dependency" in payload:
            return "TTS_ENGINE_UNAVAILABLE"
        if "kokoro file not found" in payload or "kokoro dir not found" in payload:
            return "TTS_MODEL_MISSING"
        if "text is required" in payload or "tts text invalid" in payload:
            return "TTS_TEXT_INVALID"
        if (
            "returned empty audio" in payload
            or "no samples field" in payload
            or "generated empty samples" in payload
            or "non-finite samples only" in payload
        ):
            return "TTS_AUDIO_INVALID"
        if "cancelled" in payload:
            return "TTS_RUNTIME_CANCELLED"
        return "TTS_SYNTH_FAILED"


_tts_runtime_service: TtsRuntimeService | None = None


def get_tts_runtime_service() -> TtsRuntimeService:
    global _tts_runtime_service
    if _tts_runtime_service is None:
        _tts_runtime_service = TtsRuntimeService()
    return _tts_runtime_service
