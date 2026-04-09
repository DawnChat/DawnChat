from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig
from app.plugin_ui_bridge import PluginUIBridgeError, get_ui_tool_service
from app.services.opencode_manager import get_opencode_manager
from app.utils.logger import get_logger

router = APIRouter(prefix="/opencode/mcp/ui", tags=["opencode-mcp"])
logger = get_logger("opencode_mcp_routes")


def _resolve_current_opencode_workspace_context() -> dict[str, str]:
    manager = get_opencode_manager()
    context = manager.startup_context
    workspace_kind = str(context.get("workspace_kind") or "").strip().lower()
    plugin_id = str(context.get("plugin_id") or "").strip()
    workspace_path = str(manager.workspace_path or "").strip()
    return {
        "workspace_kind": workspace_kind,
        "plugin_id": plugin_id,
        "workspace_path": workspace_path,
    }


class _UiToolServiceAdapter:
    def tool_definitions(self):
        return get_ui_tool_service().tool_definitions()

    async def execute(self, name: str, arguments: dict):
        normalized_arguments = dict(arguments or {})
        try:
            current_workspace = _resolve_current_opencode_workspace_context()
            current_plugin_id = current_workspace["plugin_id"]
            if current_workspace["workspace_kind"] == "plugin-dev" and current_plugin_id:
                requested_plugin_id = str(normalized_arguments.get("plugin_id") or "").strip()
                if requested_plugin_id and requested_plugin_id != current_plugin_id:
                    logger.warning(
                        "OpenCode UI MCP plugin context mismatch: requested=%s active=%s workspace=%s tool=%s",
                        requested_plugin_id,
                        current_plugin_id,
                        current_workspace["workspace_path"],
                        name,
                    )
                    raise PluginUIBridgeError(
                        code="plugin_context_mismatch",
                        message="requested plugin_id does not match active plugin-dev workspace",
                        details={
                            "requested_plugin_id": requested_plugin_id,
                            "active_plugin_id": current_plugin_id,
                            "active_workspace_path": current_workspace["workspace_path"],
                            "workspace_kind": current_workspace["workspace_kind"],
                        },
                    )
                if not requested_plugin_id:
                    normalized_arguments["plugin_id"] = current_plugin_id
            return await get_ui_tool_service().execute(name, normalized_arguments)
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
