from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, AsyncIterator, Dict, List
import uuid

from app.ai.base import Message
from app.utils.logger import get_logger

logger = get_logger("agentv3_runtime")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(slots=True)
class AssembledToolCall:
    source_key: str
    call_id: str
    tool_name: str
    raw_arguments: str


class ToolCallAssembler:
    def __init__(self):
        self._items: Dict[str, Dict[str, Any]] = {}
        self._order: List[str] = []

    def push(self, chunk: Any) -> None:
        if getattr(chunk, "type", "") != "tool_call_delta":
            return
        call_id = str(getattr(chunk, "call_id", "") or "")
        call_index = getattr(chunk, "call_index", None)
        key = call_id or f"idx_{call_index if isinstance(call_index, int) else len(self._items)}"
        if key not in self._items:
            self._items[key] = {"call_id": call_id, "tool_name": "", "arguments": ""}
            self._order.append(key)
        if call_id:
            self._items[key]["call_id"] = call_id
        name_delta = str(getattr(chunk, "tool_name_delta", "") or "")
        args_delta = str(getattr(chunk, "tool_arguments_delta", "") or "")
        if name_delta:
            self._items[key]["tool_name"] += name_delta
        if args_delta:
            self._items[key]["arguments"] += args_delta

    def finalize(self) -> List[AssembledToolCall]:
        result: List[AssembledToolCall] = []
        for key in self._order:
            item = self._items.get(key) or {}
            name = str(item.get("tool_name") or "").strip()
            if not name:
                continue
            raw_args = str(item.get("arguments") or "")
            result.append(
                AssembledToolCall(
                    source_key=key,
                    call_id=str(item.get("call_id") or _id("call")),
                    tool_name=name,
                    raw_arguments=raw_args,
                )
            )
        return result

    def diagnostics(self) -> List[Dict[str, str]]:
        rows: List[Dict[str, str]] = []
        for key in self._order:
            item = self._items.get(key) or {}
            rows.append(
                {
                    "key": key,
                    "call_id": str(item.get("call_id") or ""),
                    "tool_name": str(item.get("tool_name") or ""),
                    "arguments_preview": str(item.get("arguments") or "")[:180],
                }
            )
        return rows


class RuntimeToolCallFlow:
    def __init__(self, owner):
        self._owner = owner

    async def execute(
        self,
        *,
        run_input: Any,
        message_id: str,
        info: Dict[str, Any],
        assembled_calls: List[AssembledToolCall],
        tool_parts_by_key: Dict[str, str],
        state: Dict[str, Any],
        step_state: Dict[str, Any],
    ) -> AsyncIterator[Dict[str, Any]]:
        if assembled_calls and state.get("is_last_step"):
            logger.warning(
                "runtime dropped tool calls on last step session=%s message=%s count=%s",
                run_input.session_id,
                message_id,
                len(assembled_calls),
            )
            if not str(state.get("text_collected") or "").strip():
                state["text_collected"] = "达到最大执行步数，已停止工具调用。请根据已有结果继续下一步。"
            step_state["max_steps_soft_stop"] = True
            assembled_calls = []

        if not assembled_calls:
            state["assembled_calls"] = assembled_calls
            return

        logger.info(
            "runtime tool calls assembled session=%s message=%s count=%s",
            run_input.session_id,
            message_id,
            len(assembled_calls),
        )
        for call in assembled_calls:
            part_key = call.source_key
            tool_part_id = tool_parts_by_key.get(part_key) or _id("part")
            tool_parts_by_key[part_key] = tool_part_id
            yield self._owner._event(
                "tool.input.end",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "sessionID": run_input.session_id,
                    "messageID": message_id,
                    "partID": tool_part_id,
                    "callID": call.call_id,
                    "toolName": call.tool_name,
                    "rawArguments": call.raw_arguments,
                },
            )
            tool_args = self._owner._tool_executor.parse_arguments(call.raw_arguments)
            target = str(tool_args.get("file_path") or tool_args.get("path") or tool_args.get("command") or "*")
            permission_action = self._owner._tool_executor.decide_permission(
                call.tool_name,
                target,
                run_input.permission_rules,
                run_input.permission_default_action,
            )
            yield self._owner._event(
                "tool.call",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "sessionID": run_input.session_id,
                    "messageID": message_id,
                    "partID": tool_part_id,
                    "callID": call.call_id,
                    "tool": call.tool_name,
                    "input": tool_args,
                },
            )
            if permission_action == "deny":
                summary_message = f"工具 `{call.tool_name}` 被权限策略拒绝，本轮已停止。请调整权限后重试。"
                yield self._owner._event(
                    "message.part.updated",
                    run_input.session_id,
                    message_id=message_id,
                    properties={
                        "part": self._owner._build_tool_part(
                            message_id=message_id,
                            part_id=tool_part_id,
                            tool_name=call.tool_name,
                            call_id=call.call_id,
                            args=tool_args,
                            status="error",
                            error="permission_denied",
                            workspace_path=run_input.workspace_path,
                        )
                    },
                )
                yield self._owner._event(
                    "tool.error",
                    run_input.session_id,
                    message_id=message_id,
                    properties={
                        "sessionID": run_input.session_id,
                        "messageID": message_id,
                        "partID": tool_part_id,
                        "callID": call.call_id,
                        "tool": call.tool_name,
                        "error": "permission_denied",
                    },
                )
                _, summary_events = self._owner._build_fatal_summary_events(
                    run_input.session_id,
                    f"permission denied: {call.tool_name}",
                    summary_message,
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
                            f"步骤终止: permission denied: {call.tool_name}",
                        )
                    },
                )
                yield self._owner._event(
                    "session.error",
                    run_input.session_id,
                    properties={"message": f"permission denied: {call.tool_name}"},
                )
                step_state["status"] = "error"
                step_state["next_messages"] = []
                state["terminal"] = True
                return
            if permission_action == "ask":
                request_id = _id("perm")
                yield self._owner._event(
                    "message.part.updated",
                    run_input.session_id,
                    message_id=message_id,
                    properties={
                        "part": self._owner._build_tool_part(
                            message_id=message_id,
                            part_id=tool_part_id,
                            tool_name=call.tool_name,
                            call_id=call.call_id,
                            args=tool_args,
                            status="pending",
                            workspace_path=run_input.workspace_path,
                        )
                    },
                )
                yield self._owner._event(
                    "permission.asked",
                    run_input.session_id,
                    message_id=message_id,
                    properties={
                        "sessionID": run_input.session_id,
                        "permission": {
                            "id": request_id,
                            "sessionID": run_input.session_id,
                            "messageID": message_id,
                            "partID": tool_part_id,
                            "tool": call.tool_name,
                            "callID": call.call_id,
                            "pattern": target,
                            "input": tool_args,
                            "continuation": {
                                "sessionID": run_input.session_id,
                                "messageID": message_id,
                                "partID": tool_part_id,
                                "tool": call.tool_name,
                                "callID": call.call_id,
                                "input": tool_args,
                            },
                        },
                    },
                )
                yield self._owner._event(
                    "message.part.updated",
                    run_input.session_id,
                    message_id=message_id,
                    properties={
                        "part": {
                            "id": _id("part"),
                            "type": "text",
                            "messageID": message_id,
                            "text": f"工具 `{call.tool_name}` 需要授权后才能继续，请先处理权限请求。",
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
                    properties={
                        "part": self._owner._build_step_part(
                            message_id,
                            step_finish_id,
                            "step-finish",
                            f"等待权限: {call.tool_name}",
                        )
                    },
                )
                step_state["status"] = "blocked"
                step_state["next_messages"] = []
                state["terminal"] = True
                return

            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "part": self._owner._build_tool_part(
                        message_id=message_id,
                        part_id=tool_part_id,
                        tool_name=call.tool_name,
                        call_id=call.call_id,
                        args=tool_args,
                        status="running",
                        workspace_path=run_input.workspace_path,
                    )
                },
            )
            retry_count = 0
            tool_result = await self._owner._registry.execute(
                call.tool_name,
                tool_args,
                {"workspace_path": run_input.workspace_path, "plugin_id": run_input.plugin_id or ""},
            )
            policy = self._owner._tool_executor.decide_tool_failure_policy(tool_result, retry_count=retry_count)
            while policy == "retry_step":
                retry_count += 1
                self._owner._mark_branch_hit(
                    "retry_step",
                    session_id=run_input.session_id,
                    tool=call.tool_name,
                    retry_count=retry_count,
                )
                tool_result = await self._owner._registry.execute(
                    call.tool_name,
                    tool_args,
                    {"workspace_path": run_input.workspace_path, "plugin_id": run_input.plugin_id or ""},
                )
                policy = self._owner._tool_executor.decide_tool_failure_policy(tool_result, retry_count=retry_count)
            ok = bool(tool_result.get("ok"))
            output_text = self._owner._tool_executor.tool_result_text(tool_result, call.tool_name)
            tool_error_text = self._owner._tool_executor.tool_error_text(tool_result)
            if not ok:
                state["has_tool_failure"] = True
                state["tool_failure_signature"] = self._owner._tool_executor.tool_failure_signature(call.tool_name, tool_args)
                state["tool_failure_detail"] = tool_error_text
            yield self._owner._event(
                "message.part.updated",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "part": self._owner._build_tool_part(
                        message_id=message_id,
                        part_id=tool_part_id,
                        tool_name=call.tool_name,
                        call_id=call.call_id,
                        args=tool_args,
                        status="completed" if ok else "error",
                        output=output_text,
                        error=None if ok else tool_error_text,
                        workspace_path=run_input.workspace_path,
                    )
                },
            )
            yield self._owner._event(
                "tool.result" if ok else "tool.error",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "sessionID": run_input.session_id,
                    "messageID": message_id,
                    "partID": tool_part_id,
                    "callID": call.call_id,
                    "tool": call.tool_name,
                    "ok": ok,
                    "output": output_text if ok else "",
                    "error": None if ok else tool_error_text,
                    "error_code": None if ok else str(tool_result.get("error_code") or ""),
                    "retryable": None if ok else bool(tool_result.get("retryable")),
                },
            )
            if not ok and policy == "stop_error":
                stop_reason = str(tool_result.get("error_code") or "tool_non_retryable_failure")
                _, summary_events = self._owner._build_fatal_summary_events(
                    run_input.session_id,
                    stop_reason,
                    f"工具 `{call.tool_name}` 执行失败且不可自动恢复：{tool_error_text}。本轮已停止，请修正参数或更换工具后重试。",
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
                            f"步骤终止: {stop_reason}",
                        )
                    },
                )
                yield self._owner._event(
                    "session.error",
                    run_input.session_id,
                    properties={"message": stop_reason, "detail": tool_error_text, "tool": call.tool_name},
                )
                step_state["status"] = "error"
                step_state["next_messages"] = []
                step_state["has_tool_failure"] = True
                step_state["failure_signature"] = state["tool_failure_signature"]
                step_state["failure_detail"] = state["tool_failure_detail"]
                step_state["has_text_output"] = bool(str(state.get("text_collected") or "").strip())
                state["terminal"] = True
                return
            state["tool_calls_for_model"].append(
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {"name": call.tool_name, "arguments": json.dumps(tool_args, ensure_ascii=False)},
                }
            )
            state["tool_result_messages"].append(
                Message(role="tool", content=output_text, tool_call_id=call.call_id)
            )

        state["assembled_calls"] = assembled_calls
