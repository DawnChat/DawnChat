from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid

from app.agentv3.ai.gateway import AgentV3AIGateway
from app.agentv3.policy.permission_engine import PermissionEngine
from app.agentv3.runtime.event_factory import RuntimeEventFactory
from app.agentv3.runtime.retry_policy import RuntimeRetryPolicy
from app.agentv3.runtime.step_processor import RuntimeStepProcessor
from app.agentv3.runtime.tool_executor import RuntimeToolExecutor
from app.agentv3.tools.native_tools import register_native_tools
from app.agentv3.tools.registry import ToolRegistry
from app.ai.base import Message
from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("agentv3_runtime")


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@dataclass(slots=True)
class RuntimeLoopInput:
    session_id: str
    workspace_path: str
    messages: List[Message]
    plugin_id: Optional[str] = None
    model: Optional[str] = None
    max_steps: int = 6
    context_length: Optional[int] = Config.AGENTV3_CONTEXT_LENGTH
    trace_id: Optional[str] = None
    run_id: Optional[str] = None
    permission_rules: Optional[List[Dict[str, str]]] = None
    permission_default_action: str = str(getattr(Config, "AGENTV3_PERMISSION_DEFAULT_ACTION", "allow"))
    thinking_enabled: bool = False
    thinking_effort: Optional[str] = None
    thinking_budget_tokens: Optional[int] = None

class RuntimeLoop:
    def __init__(
        self,
        gateway: Optional[AgentV3AIGateway] = None,
        registry: Optional[ToolRegistry] = None,
        permission_engine: Optional[PermissionEngine] = None,
    ):
        self._gateway = gateway or AgentV3AIGateway()
        self._registry = registry or ToolRegistry()
        self._permission_engine = permission_engine or PermissionEngine()
        self._events = RuntimeEventFactory()
        self._retry_policy = RuntimeRetryPolicy()
        self._tool_executor = RuntimeToolExecutor(self._permission_engine)
        self._step_processor = RuntimeStepProcessor(self)
        if not self._registry.list_tools():
            register_native_tools(self._registry)

    async def run(self, run_input: RuntimeLoopInput) -> AsyncIterator[Dict[str, Any]]:
        trace_id = str(run_input.trace_id or _id("trace"))
        run_id = str(run_input.run_id or _id("run"))
        model_messages = list(run_input.messages)
        logger.info(
            "runtime run start session=%s trace_id=%s run_id=%s model=%s steps=%s",
            run_input.session_id,
            trace_id,
            run_id,
            run_input.model or "default",
            run_input.max_steps,
        )
        yield self._with_trace(
            self._event(
                "run.started",
                run_input.session_id,
                properties={
                    "sessionID": run_input.session_id,
                    "model": run_input.model or "default",
                    "max_steps": run_input.max_steps,
                },
            ),
            trace_id=trace_id,
            run_id=run_id,
            step=None,
        )
        yield self._with_trace(
            self._event(
                "session.status",
                run_input.session_id,
                properties={"status": {"type": "busy"}, "legacy_status": "running"},
            ),
            trace_id=trace_id,
            run_id=run_id,
            step=None,
        )
        repeat_fail_threshold = max(1, int(getattr(Config, "AGENTV3_TOOL_REPEAT_FAIL_THRESHOLD", 3)))
        consec_fail_threshold = max(1, int(getattr(Config, "AGENTV3_TOOL_CONSEC_FAIL_THRESHOLD", 2)))
        enable_loop_guard = bool(getattr(Config, "AGENTV3_ENABLE_TOOL_LOOP_GUARD", True))
        consecutive_tool_failures = 0
        repeated_signature_failures = 0
        last_failure_signature = ""
        last_failure_detail = ""
        for step_index in range(max(1, run_input.max_steps)):
            current_step = step_index + 1
            is_last_step = current_step >= max(1, run_input.max_steps)
            step_hint = ""
            if consecutive_tool_failures > 0:
                step_hint = (
                    "上一轮工具调用失败。请基于错误信息修正参数或改用其它工具，"
                    "不要重复使用同一工具与同一参数。"
                )
            logger.debug(
                "runtime step start session=%s trace_id=%s run_id=%s step=%s",
                run_input.session_id,
                trace_id,
                run_id,
                current_step,
            )
            yield self._with_trace(
                self._event(
                    "run.step.started",
                    run_input.session_id,
                    properties={"sessionID": run_input.session_id, "step": current_step},
                ),
                trace_id=trace_id,
                run_id=run_id,
                step=current_step,
            )
            step_state: Dict[str, Any] = {
                "status": "done",
                "next_messages": [],
                "has_tool_failure": False,
                "has_text_output": False,
                "failure_signature": "",
                "failure_detail": "",
                "max_steps_soft_stop": False,
            }
            async for event in self._step_processor.run_single_stream_step(
                run_input=run_input,
                model_messages=model_messages,
                step_state=step_state,
                is_last_step=is_last_step,
                step_hint=step_hint,
            ):
                yield self._with_trace(event, trace_id=trace_id, run_id=run_id, step=current_step)
            status = str(step_state.get("status") or "done")
            logger.debug(
                "runtime step finish session=%s trace_id=%s run_id=%s step=%s status=%s",
                run_input.session_id,
                trace_id,
                run_id,
                current_step,
                status,
            )
            yield self._with_trace(
                self._event(
                    "run.step.completed",
                    run_input.session_id,
                    properties={
                        "sessionID": run_input.session_id,
                        "step": current_step,
                        "status": status,
                    },
                ),
                trace_id=trace_id,
                run_id=run_id,
                step=current_step,
            )
            if status == "error":
                logger.warning(
                    "runtime run ended with error session=%s trace_id=%s run_id=%s",
                    run_input.session_id,
                    trace_id,
                    run_id,
                )
                yield self._with_trace(
                    self._event(
                        "run.failed",
                        run_input.session_id,
                        properties={"sessionID": run_input.session_id, "step": current_step},
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                return
            if status == "done":
                max_steps_soft_stop = bool(step_state.get("max_steps_soft_stop"))
                completion_reason = "max_steps_soft_stop" if max_steps_soft_stop else "normal"
                if max_steps_soft_stop:
                    self._mark_branch_hit("max_steps_soft_stop", session_id=run_input.session_id, step=current_step)
                logger.info(
                    "runtime run completed session=%s trace_id=%s run_id=%s steps=%s reason=%s",
                    run_input.session_id,
                    trace_id,
                    run_id,
                    current_step,
                    completion_reason,
                )
                yield self._with_trace(
                    self._event(
                        "run.completed",
                        run_input.session_id,
                        properties={
                            "sessionID": run_input.session_id,
                            "steps": current_step,
                            "reason": completion_reason,
                        },
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                return
            if status == "blocked":
                logger.info(
                    "runtime run blocked by permission session=%s trace_id=%s run_id=%s step=%s",
                    run_input.session_id,
                    trace_id,
                    run_id,
                    current_step,
                )
                yield self._with_trace(
                    self._event(
                        "run.blocked",
                        run_input.session_id,
                        properties={"sessionID": run_input.session_id, "step": current_step},
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event(
                        "session.status",
                        run_input.session_id,
                        properties={"status": {"type": "idle"}, "legacy_status": "idle"},
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                return
            if bool(step_state.get("has_tool_failure")):
                failure_signature = str(step_state.get("failure_signature") or "")
                failure_detail = str(step_state.get("failure_detail") or "")
                consecutive_tool_failures += 1
                if failure_signature and failure_signature == last_failure_signature:
                    repeated_signature_failures += 1
                else:
                    repeated_signature_failures = 1
                    last_failure_signature = failure_signature
                if failure_detail:
                    last_failure_detail = failure_detail
                if enable_loop_guard and (
                    repeated_signature_failures >= repeat_fail_threshold
                    or (
                        consecutive_tool_failures >= consec_fail_threshold
                        and not bool(step_state.get("has_text_output"))
                    )
                ):
                    self._mark_branch_hit(
                        "repeated_tool_failure",
                        session_id=run_input.session_id,
                        consecutive=consecutive_tool_failures,
                        repeated=repeated_signature_failures,
                    )
                    logger.warning(
                        "runtime repeated tool failure session=%s trace_id=%s run_id=%s consecutive=%s repeated=%s signature=%s",
                        run_input.session_id,
                        trace_id,
                        run_id,
                        consecutive_tool_failures,
                        repeated_signature_failures,
                        last_failure_signature[:120],
                    )
                    summary = (
                        "检测到工具调用重复失败，已停止本轮以避免死循环。"
                        f"最近错误：{last_failure_detail or 'tool_error'}。"
                        "请修正参数、路径或改用其它工具后重试。"
                    )
                    _, summary_events = self._build_fatal_summary_events(
                        run_input.session_id,
                        "repeated_tool_failure",
                        summary,
                    )
                    for event in summary_events:
                        yield self._with_trace(event, trace_id=trace_id, run_id=run_id, step=current_step)
                    yield self._with_trace(
                        self._event(
                            "run.failed",
                            run_input.session_id,
                            properties={"sessionID": run_input.session_id, "reason": "repeated_tool_failure"},
                        ),
                        trace_id=trace_id,
                        run_id=run_id,
                        step=current_step,
                    )
                    yield self._with_trace(
                        self._event(
                            "session.error",
                            run_input.session_id,
                            properties={
                                "message": "repeated_tool_failure",
                                "detail": last_failure_detail,
                                "signature": last_failure_signature,
                            },
                        ),
                        trace_id=trace_id,
                        run_id=run_id,
                        step=current_step,
                    )
                    yield self._with_trace(
                        self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
                        trace_id=trace_id,
                        run_id=run_id,
                        step=current_step,
                    )
                    return
            else:
                consecutive_tool_failures = 0
                repeated_signature_failures = 0
                last_failure_signature = ""
            next_messages = step_state.get("next_messages")
            if isinstance(next_messages, list):
                model_messages.extend(next_messages)
            if status == "continue" and is_last_step:
                self._mark_branch_hit("max_steps_soft_stop", session_id=run_input.session_id, step=current_step)
                logger.info(
                    "runtime max steps soft stop session=%s trace_id=%s run_id=%s steps=%s",
                    run_input.session_id,
                    trace_id,
                    run_id,
                    run_input.max_steps,
                )
                _, summary_events = self._build_fatal_summary_events(
                    run_input.session_id,
                    "max_steps_soft_stop",
                    (
                        "已到达本轮最大步数，已停止继续工具调用。"
                        "以下是当前可确认结果；如需继续执行，请发送下一条指令。"
                    ),
                )
                for event in summary_events:
                    yield self._with_trace(event, trace_id=trace_id, run_id=run_id, step=current_step)
                yield self._with_trace(
                    self._event(
                        "run.completed",
                        run_input.session_id,
                        properties={
                            "sessionID": run_input.session_id,
                            "steps": current_step,
                            "reason": "max_steps_soft_stop",
                        },
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event(
                        "session.status",
                        run_input.session_id,
                        properties={"status": {"type": "idle"}, "legacy_status": "idle"},
                    ),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                yield self._with_trace(
                    self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
                    trace_id=trace_id,
                    run_id=run_id,
                    step=current_step,
                )
                return
        logger.warning(
            "runtime max steps exceeded session=%s trace_id=%s run_id=%s steps=%s",
            run_input.session_id,
            trace_id,
            run_id,
            run_input.max_steps,
        )
        _, summary_events = self._build_fatal_summary_events(
            run_input.session_id,
            "max_steps_exceeded",
            (
                "执行步数达到上限，本轮已停止。"
                + (
                    f"最近工具失败：{last_failure_detail}。"
                    if last_failure_detail
                    else ""
                )
                + "你可以缩小任务范围后重试，或让我先给出分步计划。"
            ),
        )
        for event in summary_events:
            yield self._with_trace(event, trace_id=trace_id, run_id=run_id, step=run_input.max_steps)
        yield self._with_trace(
            self._event(
                "run.failed",
                run_input.session_id,
                properties={"sessionID": run_input.session_id, "reason": "max_steps_exceeded"},
            ),
            trace_id=trace_id,
            run_id=run_id,
            step=run_input.max_steps,
        )
        yield self._with_trace(
            self._event("session.error", run_input.session_id, properties={"message": "max_steps_exceeded"}),
            trace_id=trace_id,
            run_id=run_id,
            step=run_input.max_steps,
        )
        yield self._with_trace(
            self._event("session.idle", run_input.session_id, properties={"sessionID": run_input.session_id}),
            trace_id=trace_id,
            run_id=run_id,
            step=run_input.max_steps,
        )

    def _tool_schemas(self) -> List[Dict[str, Any]]:
        tools = []
        for spec in self._registry.list_tools():
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": spec.name,
                        "description": spec.description,
                        "parameters": spec.input_schema or {"type": "object", "properties": {}},
                    },
                }
            )
        return tools

    def _build_fatal_summary_events(
        self,
        session_id: str,
        raw_error: str,
        summary_text: str,
    ) -> tuple[str, List[Dict[str, Any]]]:
        return self._events.build_fatal_summary_events(session_id, raw_error, summary_text)

    def _build_tool_part(
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
        return self._events.build_tool_part(
            message_id=message_id,
            part_id=part_id,
            tool_name=tool_name,
            call_id=call_id,
            args=args,
            status=status,
            output=output,
            error=error,
            workspace_path=workspace_path,
        )

    def _build_step_part(
        self,
        message_id: str,
        part_id: str,
        part_type: str,
        reason: str,
    ) -> Dict[str, Any]:
        return self._events.build_step_part(message_id=message_id, part_id=part_id, part_type=part_type, reason=reason)

    def _mark_branch_hit(self, branch: str, *, session_id: str, **extra: Any) -> None:
        payload: Dict[str, Any] = {"branch": branch, "session": session_id}
        for key, value in extra.items():
            if value is None:
                continue
            payload[key] = value
        logger.info("runtime branch hit %s", payload)

    def _with_trace(
        self,
        event: Dict[str, Any],
        *,
        trace_id: str,
        run_id: str,
        step: Optional[int],
    ) -> Dict[str, Any]:
        return self._events.with_trace(event, trace_id=trace_id, run_id=run_id, step=step)

    def _event(
        self,
        event_type: str,
        session_id: str,
        message_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return self._events.event(
            event_type=event_type,
            session_id=session_id,
            message_id=message_id,
            properties=properties or {},
        )

