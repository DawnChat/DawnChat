from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig
from app.plugin_ui_bridge import PluginUIBridgeError, get_ui_tool_service

router = APIRouter(prefix="/opencode/mcp/ui", tags=["opencode-mcp"])


class _UiToolServiceAdapter:
    def tool_definitions(self):
        return get_ui_tool_service().tool_definitions()

    async def execute(self, name: str, arguments: dict):
        try:
            return await get_ui_tool_service().execute(name, arguments)
        except PluginUIBridgeError as err:
            return err.to_payload()


_hub = OpenCodeMcpHub(
    OpenCodeMcpHubConfig(
        mcp_name="ui",
        server_name="dawnchat-opencode-ui-mcp",
    ),
    service_factory=lambda: _UiToolServiceAdapter(),
)


@router.post("")
async def opencode_mcp_ui(body: JsonRpcRequest):
    return await _hub.handle(body)


@router.get("")
async def opencode_mcp_ui_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
