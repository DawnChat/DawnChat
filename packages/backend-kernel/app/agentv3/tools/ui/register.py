from __future__ import annotations

from app.agentv3.tools.registry import ToolRegistry, ToolSpec
from app.plugin_ui_bridge import get_ui_tool_service
from app.plugin_ui_bridge.models import BridgeOperation

from .executors import act_executor, describe_executor, query_executor, scroll_executor, session_wait_executor


def register_ui_tools(registry: ToolRegistry) -> None:
    executor_map = {
        "dawnchat.ui.describe": describe_executor,
        "dawnchat.ui.query": query_executor,
        "dawnchat.ui.act": act_executor,
        "dawnchat.ui.scroll": scroll_executor,
        "dawnchat.ui.session.wait": session_wait_executor,
    }
    read_ops = {BridgeOperation.DESCRIBE, BridgeOperation.QUERY}

    for item in get_ui_tool_service().tool_definitions():
        executor = executor_map.get(item.name)
        if executor is None:
            continue
        registry.register(
            ToolSpec(
                name=item.name,
                description=item.description,
                capability="ui",
                permission="read" if item.op in read_ops or item.name == "dawnchat.ui.session.wait" else "edit",
                input_schema=item.input_schema,
                executor=executor,
            )
        )

