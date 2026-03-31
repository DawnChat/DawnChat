from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from app.utils.logger import get_logger

ToolExecutor = Callable[[Dict[str, Any], Dict[str, Any]], Awaitable[Dict[str, Any]]]
logger = get_logger("agentv3_tools")


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    capability: str
    permission: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    executor: Optional[ToolExecutor] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolSpec] = {}

    def register(self, tool: ToolSpec) -> None:
        self._tools[tool.name] = tool

    def list_tools(self) -> List[ToolSpec]:
        return list(self._tools.values())

    def get(self, name: str) -> Optional[ToolSpec]:
        return self._tools.get(name)

    async def execute(self, name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        tool = self._tools.get(name)
        if not tool:
            logger.warning("tool execute failed: tool_not_found name=%s", name)
            return {
                "ok": False,
                "error": f"tool_not_found: {name}",
                "error_code": "tool_not_found",
                "retryable": False,
                "root_cause_hint": "Check tool name against the registered tools list.",
            }
        if not tool.executor:
            logger.warning("tool execute failed: no_executor name=%s", name)
            return {
                "ok": False,
                "error": f"tool_no_executor: {name}",
                "error_code": "tool_no_executor",
                "retryable": False,
                "root_cause_hint": "Tool is registered without an executor implementation.",
            }
        try:
            logger.debug("tool execute start name=%s", name)
            result = await tool.executor(arguments, context)
            logger.debug("tool execute finish name=%s ok=%s", name, bool(result.get("ok")))
            return result
        except Exception as err:
            logger.error("tool execute exception name=%s error=%s", name, err, exc_info=True)
            return {
                "ok": False,
                "error": str(err),
                "error_code": "tool_exception",
                "retryable": False,
                "root_cause_hint": "Inspect tool implementation and input arguments.",
            }

