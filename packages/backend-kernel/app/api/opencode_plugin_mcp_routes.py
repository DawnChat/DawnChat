from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig
from app.services.plugin_backend_mcp_proxy_service import (
    PluginBackendMcpProxyError,
    get_plugin_backend_mcp_proxy_service,
)

router = APIRouter(prefix="/opencode/mcp/plugin/{plugin_id}/backend", tags=["opencode-mcp"])


class _BackendProxyAdapter:
    async def forward_jsonrpc(self, payload: dict, context: dict):
        plugin_id = str(context.get("plugin_id") or "").strip()
        return await get_plugin_backend_mcp_proxy_service().forward_jsonrpc(
            plugin_id=plugin_id,
            payload=payload,
        )


def _proxy_error_mapper(err: Exception) -> tuple[str, str]:
    if isinstance(err, PluginBackendMcpProxyError):
        return (err.code, err.message)
    return ("plugin_backend_proxy_failed", str(err))


_hub = OpenCodeMcpHub(
    OpenCodeMcpHubConfig(
        mcp_name="plugin_backend",
        server_name="dawnchat-opencode-plugin-backend-mcp-proxy",
        mode="jsonrpc_proxy",
    ),
    proxy_factory=lambda: _BackendProxyAdapter(),
    proxy_error_mapper=_proxy_error_mapper,
)


@router.post("")
async def opencode_plugin_backend_mcp(plugin_id: str, body: JsonRpcRequest):
    return await _hub.handle(body, context={"plugin_id": plugin_id})


@router.get("")
async def opencode_plugin_backend_mcp_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
