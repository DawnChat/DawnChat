from __future__ import annotations

from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import (
    JsonRpcRequest,
    jsonrpc_error_from_internal,
    jsonrpc_invalid_params,
    jsonrpc_method_not_found,
    jsonrpc_response,
    to_mcp_tool_result,
)
from app.services.iwp_mcp_service import get_iwp_mcp_service
from app.utils.logger import get_logger

router = APIRouter(prefix="/opencode/mcp/iwp", tags=["opencode-mcp"])
logger = get_logger("opencode_mcp_iwp_routes")


@router.post("")
async def opencode_mcp_iwp(body: JsonRpcRequest):
    started_at = perf_counter()
    params = body.params or {}
    error_code = ""
    if body.method == "initialize":
        response = jsonrpc_response(
            body.id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dawnchat-opencode-iwp-mcp", "version": "0.1.0"},
            },
        )
    elif body.method == "tools/list":
        response = jsonrpc_response(body.id, {"tools": get_iwp_mcp_service().tool_definitions()})
    elif body.method == "tools/call":
        name = str(params.get("name") or "").strip()
        raw_arguments = params.get("arguments")
        arguments = (
            {str(key): value for key, value in raw_arguments.items()}
            if isinstance(raw_arguments, dict)
            else {}
        )
        if not name:
            error_code = "invalid_arguments"
            response = jsonrpc_invalid_params(body.id, "missing tool name")
        else:
            result = await get_iwp_mcp_service().execute(name, arguments)
            ok = bool(result.get("ok", True))
            if ok:
                response = jsonrpc_response(body.id, to_mcp_tool_result(result))
            else:
                error_code = str(result.get("error_code") or "tool_execution_failed")
                message = str(result.get("message") or "tool execution failed")
                details = result.get("details")
                data = {"payload": result}
                if isinstance(details, dict) and details:
                    data["details"] = details
                response = jsonrpc_error_from_internal(body.id, error_code, message, data)
    else:
        error_code = "method_not_found"
        response = jsonrpc_method_not_found(body.id, body.method)
    logger.info(
        "[opencode_mcp_iwp] method=%s request_id=%s mcp_name=iwp latency_ms=%s error_code=%s",
        body.method,
        body.id,
        int((perf_counter() - started_at) * 1000),
        error_code,
    )
    return response


@router.get("")
async def opencode_mcp_iwp_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
