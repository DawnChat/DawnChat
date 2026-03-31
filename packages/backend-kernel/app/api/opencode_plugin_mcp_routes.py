from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import (
    JsonRpcRequest,
    jsonrpc_error_from_internal,
    jsonrpc_method_not_found,
    jsonrpc_response,
)
from app.services.plugin_backend_mcp_proxy_service import (
    PluginBackendMcpProxyError,
    get_plugin_backend_mcp_proxy_service,
)
from app.utils.logger import get_logger

router = APIRouter(prefix="/opencode/mcp/plugin/{plugin_id}/backend", tags=["opencode-mcp"])
logger = get_logger("opencode_plugin_backend_mcp_routes")


@router.post("")
async def opencode_plugin_backend_mcp(plugin_id: str, body: JsonRpcRequest):
    started_at = perf_counter()
    error_code = ""
    if body.method == "initialize":
        response = jsonrpc_response(
            body.id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "dawnchat-opencode-plugin-backend-mcp-proxy",
                    "version": "0.1.0",
                },
            },
        )
    elif body.method not in {"tools/list", "tools/call"}:
        error_code = "method_not_found"
        response = jsonrpc_method_not_found(body.id, body.method)
    else:
        payload = body.model_dump(mode="python", exclude_none=True)
        try:
            response = await get_plugin_backend_mcp_proxy_service().forward_jsonrpc(
                plugin_id=plugin_id,
                payload=payload,
            )
        except PluginBackendMcpProxyError as err:
            error_code = err.code
            response = jsonrpc_error_from_internal(body.id, err.code, err.message)
    logger.info(
        "[opencode_plugin_backend_mcp] method=%s request_id=%s plugin_id=%s mcp_name=plugin_backend latency_ms=%s error_code=%s",
        body.method,
        body.id,
        plugin_id,
        int((perf_counter() - started_at) * 1000),
        error_code,
    )
    return response


@router.get("")
async def opencode_plugin_backend_mcp_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
