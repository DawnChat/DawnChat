from __future__ import annotations

from typing import Any, AsyncIterator, Dict
import uuid

from app.ai.base import Message


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class RuntimeFinalizeFlow:
    def __init__(self, owner):
        self._owner = owner

    async def finalize_with_tools(
        self,
        *,
        run_input: Any,
        message_id: str,
        info: Dict[str, Any],
        state: Dict[str, Any],
        step_state: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        reasoning_part_id = state.get("reasoning_part_id")
        if reasoning_part_id:
            yield self._owner._event(
                "reasoning.end",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "sessionID": run_input.session_id,
                    "messageID": message_id,
                    "partID": reasoning_part_id,
                },
            )
            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "part": {
                        "id": reasoning_part_id,
                        "type": "reasoning",
                        "messageID": message_id,
                        "text": state.get("reasoning_collected", ""),
                        "time": {"end": state["now_iso"]()},
                    }
                },
            )
        info["time"]["completed"] = state["now_iso"]()
        yield self._owner._event("message.updated", run_input.session_id, message_id=message_id, properties={"info": info})
        step_finish_id = _id("part")
        assembled_calls = state.get("assembled_calls") or []
        yield self._owner._event(
            "message.part.updated",
            run_input.session_id,
            message_id=message_id,
            properties={
                "part": self._owner._build_step_part(
                    message_id,
                    step_finish_id,
                    "step-finish",
                    f"步骤完成: 执行了 {len(assembled_calls)} 个工具",
                )
            },
        )
        assistant_msg = Message(
            role="assistant",
            content=state.get("text_collected", ""),
            tool_calls=state.get("tool_calls_for_model") or [],
        )
        next_messages = [assistant_msg]
        next_messages.extend(state.get("tool_result_messages") or [])
        step_state["status"] = "continue"
        step_state["next_messages"] = next_messages
        step_state["has_tool_failure"] = bool(state.get("has_tool_failure"))
        step_state["failure_signature"] = str(state.get("tool_failure_signature") or "")
        step_state["failure_detail"] = str(state.get("tool_failure_detail") or "")
        step_state["has_text_output"] = bool(str(state.get("text_collected") or "").strip())

    async def finalize_without_tools(
        self,
        *,
        run_input: Any,
        message_id: str,
        info: Dict[str, Any],
        state: Dict[str, Any],
        step_state: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        text_collected = str(state.get("text_collected") or "")
        reasoning_part_id = state.get("reasoning_part_id")
        if not text_collected.strip():
            _, summary_events = self._owner._build_fatal_summary_events(
                run_input.session_id,
                "empty_assistant_output",
                "模型未生成可展示的最终回答，本轮已停止。请重试，或切换模型后继续。",
            )
            for event in summary_events:
                yield event
            step_finish_id = _id("part")
            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "part": self._owner._build_step_part(
                        message_id,
                        step_finish_id,
                        "step-finish",
                        "步骤终止: empty_assistant_output",
                    )
                },
            )
            yield self._owner._event(
                "session.error",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "message": "empty_assistant_output",
                    "model": run_input.model or "default",
                    "workspace_path": run_input.workspace_path,
                },
            )
            step_state["status"] = "error"
            step_state["next_messages"] = []
            return
        text_part_id = state.get("text_part_id")
        if text_part_id:
            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={"part": {"id": text_part_id, "type": "text", "messageID": message_id, "text": text_collected}},
            )
        if reasoning_part_id:
            yield self._owner._event(
                "reasoning.end",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "sessionID": run_input.session_id,
                    "messageID": message_id,
                    "partID": reasoning_part_id,
                },
            )
            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "part": {
                        "id": reasoning_part_id,
                        "type": "reasoning",
                        "messageID": message_id,
                        "text": state.get("reasoning_collected", ""),
                        "time": {"end": state["now_iso"]()},
                    }
                },
            )
        info["time"]["completed"] = state["now_iso"]()
        yield self._owner._event("message.updated", run_input.session_id, message_id=message_id, properties={"info": info})
        step_finish_id = _id("part")
        yield self._owner._event(
            "message.part.updated",
            run_input.session_id,
            message_id=message_id,
            properties={"part": self._owner._build_step_part(message_id, step_finish_id, "step-finish", "步骤完成")},
        )
        step_state["status"] = "done"
        step_state["next_messages"] = [Message(role="assistant", content=text_collected)]
