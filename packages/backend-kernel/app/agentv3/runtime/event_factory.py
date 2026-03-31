from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid

from app.agentv3.runtime.events import RunEvent


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RuntimeEventFactory:
    def event(
        self,
        event_type: str,
        session_id: str,
        message_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return RunEvent(
            type=event_type,
            session_id=session_id,
            message_id=message_id,
            properties=properties or {},
        ).to_payload()

    def with_trace(
        self,
        event: Dict[str, Any],
        *,
        trace_id: str,
        run_id: str,
        step: Optional[int],
    ) -> Dict[str, Any]:
        next_event = dict(event)
        raw_props = next_event.get("properties")
        props = dict(raw_props) if isinstance(raw_props, dict) else {}
        props.setdefault("trace_id", trace_id)
        props.setdefault("run_id", run_id)
        if step is not None:
            props.setdefault("step", step)
        next_event["properties"] = props
        return next_event

    def build_fatal_summary_events(
        self,
        session_id: str,
        raw_error: str,
        summary_text: str,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        message_id = _id("msg")
        part_id = _id("part")
        info = {
            "id": message_id,
            "role": "assistant",
            "sessionID": session_id,
            "time": {"created": _now_iso(), "completed": _now_iso()},
            "error": {"message": raw_error},
        }
        events = [
            self.event("message.updated", session_id, message_id=message_id, properties={"info": info}),
            self.event(
                "message.part.updated",
                session_id,
                message_id=message_id,
                properties={"part": {"id": part_id, "type": "text", "messageID": message_id, "text": summary_text}},
            ),
        ]
        return message_id, events

    def build_tool_part(
        self,
        message_id: str,
        part_id: str,
        tool_name: str,
        call_id: str,
        args: Dict[str, Any],
        status: str,
        output: str = "",
        error: Optional[str] = None,
        workspace_path: str = "",
    ) -> Dict[str, Any]:
        state: Dict[str, Any] = {"status": status, "input": args}
        if output:
            state["output"] = output
        if error:
            state["error"] = error
        if workspace_path:
            state["workspace_path"] = workspace_path
        return {
            "id": part_id,
            "type": "tool",
            "messageID": message_id,
            "tool": tool_name,
            "callID": call_id,
            "state": state,
        }

    def build_step_part(
        self,
        message_id: str,
        part_id: str,
        part_type: str,
        reason: str,
    ) -> Dict[str, Any]:
        return {
            "id": part_id,
            "type": part_type,
            "messageID": message_id,
            "reason": reason,
        }
