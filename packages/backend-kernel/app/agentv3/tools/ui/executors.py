from __future__ import annotations

from typing import Any, Dict

from app.plugin_ui_bridge import PluginUIBridgeError, get_ui_tool_service


def _resolve_plugin_id(arguments: Dict[str, Any], context: Dict[str, Any]) -> str:
    plugin_id = str(arguments.get("plugin_id") or context.get("plugin_id") or "").strip()
    return plugin_id


def _normalize_tool_result(result: Dict[str, Any]) -> Dict[str, Any]:
    if bool(result.get("ok")):
        return {"ok": True, "data": result}
    return {
        "ok": False,
        "error": str(result.get("message") or result.get("error") or "ui_bridge_failed"),
        "error_code": str(result.get("error_code") or "ui_bridge_failed"),
        "retryable": False,
    }


async def _execute_ui_tool(tool_name: str, arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    plugin_id = _resolve_plugin_id(arguments, context)
    if not plugin_id:
        return {"ok": False, "error": "missing plugin_id", "error_code": "missing_plugin_id", "retryable": False}
    payload = dict(arguments)
    payload["plugin_id"] = plugin_id
    try:
        result = await get_ui_tool_service().execute(tool_name, payload)
        return _normalize_tool_result(result)
    except PluginUIBridgeError as err:
        return {"ok": False, "error": err.message, "error_code": err.code, "retryable": False}


async def describe_executor(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return await _execute_ui_tool("dawnchat.ui.describe", arguments, context)


async def query_executor(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return await _execute_ui_tool("dawnchat.ui.query", arguments, context)


async def act_executor(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return await _execute_ui_tool("dawnchat.ui.act", arguments, context)


async def scroll_executor(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return await _execute_ui_tool("dawnchat.ui.scroll", arguments, context)


async def session_wait_executor(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    return await _execute_ui_tool("dawnchat.ui.session.wait", arguments, context)

