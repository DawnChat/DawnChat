from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid

from app.agentv3.ai.gateway import GatewayRequest
from app.agentv3.runtime.finalize_flow import RuntimeFinalizeFlow
from app.agentv3.runtime.tool_call_flow import RuntimeToolCallFlow, ToolCallAssembler
from app.ai.base import Message
from app.utils.logger import get_logger

logger = get_logger("agentv3_runtime")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

class RuntimeStreamConsumer:
    def __init__(self, owner):
        self._owner = owner
        self._tool_flow = RuntimeToolCallFlow(owner)
        self._finalize_flow = RuntimeFinalizeFlow(owner)

    async def run_single_stream_step(
        self,
        run_input: Any,
        model_messages: List[Message],
        step_state: Dict[str, Any],
        *,
        is_last_step: bool = False,
        step_hint: str = "",
    ) -> AsyncIterator[Dict[str, Any]]:
        message_id = _id("msg")
        first_stream_delta = False
        text_part_id: Optional[str] = None
        reasoning_part_id: Optional[str] = None
        text_collected = ""
        reasoning_collected = ""
        assembler = ToolCallAssembler()
        tool_calls_for_model: List[Dict[str, Any]] = []
        tool_result_messages: List[Message] = []
        has_tool_failure = False
        tool_failure_signature = ""
        tool_failure_detail = ""
        info = {
            "id": message_id,
            "role": "assistant",
            "sessionID": run_input.session_id,
            "time": {"created": _now_iso()},
            "error": None,
        }
        yield self._owner._event("message.updated", run_input.session_id, message_id=message_id, properties={"info": info})
        step_start_id = _id("part")
        yield self._owner._event(
            "message.part.updated",
            run_input.session_id,
            message_id=message_id,
            properties={"part": self._owner._build_step_part(message_id, step_start_id, "step-start", "步骤开始执行")},
        )
        yield self._owner._event(
            "run.progress",
            run_input.session_id,
            message_id=message_id,
            properties={
                "sessionID": run_input.session_id,
                "messageID": message_id,
                "status": "streaming",
                "detail": "等待模型首个增量输出",
            },
        )

        stream_error: Optional[str] = None
        text_delta_count = 0
        reasoning_delta_count = 0
        tool_call_delta_count = 0
        tools_enabled = not is_last_step
        tool_choice = "auto" if tools_enabled else "none"
        tool_schemas = self._owner._tool_schemas() if tools_enabled else []
        model_request_messages = list(model_messages)
        if step_hint or is_last_step:
            hint_chunks: List[str] = []
            if step_hint:
                hint_chunks.append(step_hint)
            if is_last_step:
                hint_chunks.append("这是最后一步。禁止调用任何工具，请仅输出文本总结、剩余风险和下一步建议。")
            model_request_messages.append(
                Message(role="system", content="\n".join(hint_chunks))
            )
        tool_parts_by_key: Dict[str, str] = {}
        tool_input_name_by_key: Dict[str, str] = {}
        tool_input_raw_by_key: Dict[str, str] = {}
        tool_input_signature_seen: set[str] = set()
        reasoning_placeholder_seen: set[str] = set()
        for attempt in range(2):
            stream_error = None
            async for chunk in self._owner._gateway.stream(
                GatewayRequest(
                    messages=model_request_messages,
                    model=run_input.model,
                    context_length=run_input.context_length,
                    tools=tool_schemas,
                    tool_choice=tool_choice,
                    thinking_enabled=run_input.thinking_enabled,
                    thinking_effort=run_input.thinking_effort,
                    thinking_budget_tokens=run_input.thinking_budget_tokens,
                )
            ):
                if chunk.type == "error":
                    stream_error = chunk.error or "model_stream_error"
                    break
                if chunk.type == "text_delta" and chunk.text:
                    text_delta_count += 1
                    if not first_stream_delta:
                        first_stream_delta = True
                        logger.info(
                            "runtime first delta session=%s message=%s kind=text",
                            run_input.session_id,
                            message_id,
                        )
                    if not text_part_id:
                        text_part_id = _id("part")
                        yield self._owner._event(
                            "message.part.updated",
                            run_input.session_id,
                            message_id=message_id,
                            properties={"part": {"id": text_part_id, "type": "text", "messageID": message_id, "text": ""}},
                        )
                    text_collected += chunk.text
                    yield self._owner._event(
                        "message.part.delta",
                        run_input.session_id,
                        message_id=message_id,
                        properties={
                            "sessionID": run_input.session_id,
                            "messageID": message_id,
                            "partID": text_part_id,
                            "partType": "text",
                            "field": "text",
                            "delta": chunk.text,
                        },
                    )
                    continue
                if chunk.type == "reasoning_delta" and chunk.text:
                    chunk_metadata = getattr(chunk, "metadata", {}) or {}
                    placeholder_signature = str(chunk_metadata.get("placeholder_signature") or "").strip()
                    if placeholder_signature and placeholder_signature in reasoning_placeholder_seen:
                        continue
                    if placeholder_signature:
                        reasoning_placeholder_seen.add(placeholder_signature)
                    reasoning_delta_count += 1
                    if not first_stream_delta:
                        first_stream_delta = True
                        logger.info(
                            "runtime first delta session=%s message=%s kind=reasoning",
                            run_input.session_id,
                            message_id,
                        )
                    if not reasoning_part_id:
                        reasoning_part_id = _id("part")
                        yield self._owner._event(
                            "reasoning.start",
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
                                    "text": "",
                                }
                            },
                        )
                    reasoning_collected += chunk.text
                    yield self._owner._event(
                        "message.part.delta",
                        run_input.session_id,
                        message_id=message_id,
                        properties={
                            "sessionID": run_input.session_id,
                            "messageID": message_id,
                            "partID": reasoning_part_id,
                            "partType": "reasoning",
                            "field": "text",
                            "delta": chunk.text,
                        },
                    )
                    yield self._owner._event(
                        "reasoning.delta",
                        run_input.session_id,
                        message_id=message_id,
                        properties={
                            "sessionID": run_input.session_id,
                            "messageID": message_id,
                            "partID": reasoning_part_id,
                            "delta": chunk.text,
                        },
                    )
                    continue
                if chunk.type == "tool_call_delta":
                    tool_call_delta_count += 1
                    if not first_stream_delta:
                        first_stream_delta = True
                        logger.info(
                            "runtime first delta session=%s message=%s kind=tool_call",
                            run_input.session_id,
                            message_id,
                        )
                    key = str(chunk.call_id or f"idx_{chunk.call_index if isinstance(chunk.call_index, int) else 0}")
                    part_id = tool_parts_by_key.get(key)
                    if not part_id:
                        part_id = _id("part")
                        tool_parts_by_key[key] = part_id
                        yield self._owner._event(
                            "tool.input.start",
                            run_input.session_id,
                            message_id=message_id,
                            properties={
                                "sessionID": run_input.session_id,
                                "messageID": message_id,
                                "partID": part_id,
                                "callID": chunk.call_id,
                                "callIndex": chunk.call_index,
                            },
                        )
                    if chunk.tool_name_delta:
                        tool_input_name_by_key[key] = f"{tool_input_name_by_key.get(key, '')}{chunk.tool_name_delta}"
                    if chunk.tool_arguments_delta:
                        tool_input_raw_by_key[key] = f"{tool_input_raw_by_key.get(key, '')}{chunk.tool_arguments_delta}"
                    tool_name_preview = tool_input_name_by_key.get(key, "")
                    args_preview = tool_input_raw_by_key.get(key, "")
                    signature = (
                        f"{key}:{chunk.call_id}:{tool_name_preview}:{args_preview}:{chunk.tool_name_delta}:{chunk.tool_arguments_delta}"
                    )
                    if signature not in tool_input_signature_seen:
                        tool_input_signature_seen.add(signature)
                        yield self._owner._event(
                            "tool.input.delta",
                            run_input.session_id,
                            message_id=message_id,
                            properties={
                                "sessionID": run_input.session_id,
                                "messageID": message_id,
                                "partID": part_id,
                                "callID": chunk.call_id,
                                "callIndex": chunk.call_index,
                                "toolNameDelta": chunk.tool_name_delta,
                                "argumentsDelta": chunk.tool_arguments_delta,
                                "toolName": tool_name_preview,
                                "rawArguments": args_preview,
                                "toolNamePreview": tool_name_preview,
                                "rawArgumentsPreview": args_preview,
                                "source": "tool_call_delta",
                            },
                        )
                    assembler.push(chunk)
                    continue
                if chunk.type == "end":
                    break
            if not stream_error:
                break
            if attempt == 0 and self._owner._retry_policy.should_retry_stream_error(stream_error):
                self._owner._mark_branch_hit(
                    "stream_retry_sanitize",
                    session_id=run_input.session_id,
                    attempt=attempt + 1,
                )
                model_request_messages = self._owner._retry_policy.sanitize_messages_for_retry(
                    model_request_messages,
                    id_factory=_id,
                )
                continue
            fatal_summary = self._owner._retry_policy.build_stream_error_summary(stream_error)
            _, summary_events = self._owner._build_fatal_summary_events(
                run_input.session_id,
                stream_error,
                fatal_summary,
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
                        f"步骤终止: {stream_error}",
                    )
                },
            )
            yield self._owner._event(
                "session.error",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "message": stream_error,
                    "model": run_input.model or "default",
                    "workspace_path": run_input.workspace_path,
                    "attempt": attempt + 1,
                },
            )
            step_state["status"] = "error"
            step_state["next_messages"] = []
            return

        assembled_calls = assembler.finalize()
        logger.info(
            "runtime step chunk summary session=%s message=%s text=%s reasoning=%s tool_call_delta=%s assembled=%s",
            run_input.session_id,
            message_id,
            text_delta_count,
            reasoning_delta_count,
            tool_call_delta_count,
            len(assembled_calls),
        )
        if reasoning_delta_count == 0:
            logger.debug(
                "runtime no reasoning delta session=%s message=%s model=%s",
                run_input.session_id,
                message_id,
                run_input.model or "default",
            )
        if tool_call_delta_count > 0 and not assembled_calls:
            diag_rows = assembler.diagnostics()
            logger.error(
                "runtime tool_call assembly failed session=%s message=%s diagnostics=%s",
                run_input.session_id,
                message_id,
                diag_rows,
            )
            yield self._owner._event(
                "session.error",
                run_input.session_id,
                message_id=message_id,
                properties={
                    "message": "tool_call_assembly_failed",
                    "model": run_input.model or "default",
                    "workspace_path": run_input.workspace_path,
                    "diagnostics": diag_rows,
                },
            )
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
                        "步骤终止: tool_call_assembly_failed",
                    )
                },
            )
            step_state["status"] = "error"
            step_state["next_messages"] = []
            return
        flow_state: Dict[str, Any] = {
            "is_last_step": is_last_step,
            "text_collected": text_collected,
            "reasoning_collected": reasoning_collected,
            "reasoning_part_id": reasoning_part_id,
            "text_part_id": text_part_id,
            "tool_calls_for_model": tool_calls_for_model,
            "tool_result_messages": tool_result_messages,
            "has_tool_failure": has_tool_failure,
            "tool_failure_signature": tool_failure_signature,
            "tool_failure_detail": tool_failure_detail,
            "assembled_calls": assembled_calls,
            "terminal": False,
            "now_iso": _now_iso,
        }
        async for event in self._tool_flow.execute(
            run_input=run_input,
            message_id=message_id,
            info=info,
            assembled_calls=assembled_calls,
            tool_parts_by_key=tool_parts_by_key,
            state=flow_state,
            step_state=step_state,
        ):
            yield event
        if flow_state.get("terminal"):
            return
        if flow_state.get("assembled_calls"):
            async for event in self._finalize_flow.finalize_with_tools(
                run_input=run_input,
                message_id=message_id,
                info=info,
                state=flow_state,
                step_state=step_state,
            ):
                yield event
            return
        async for event in self._finalize_flow.finalize_without_tools(
            run_input=run_input,
            message_id=message_id,
            info=info,
            state=flow_state,
            step_state=step_state,
        ):
            yield event

