from __future__ import annotations

from time import perf_counter
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import (
    JsonRpcRequest,
    jsonrpc_error_from_internal,
    jsonrpc_invalid_params,
    jsonrpc_method_not_found,
    jsonrpc_response,
    to_mcp_tool_result,
)
from app.utils.logger import get_logger
from app.voice import get_voice_mcp_service

router = APIRouter(prefix="/opencode/mcp/voice", tags=["opencode-mcp"])
logger = get_logger("opencode_mcp_voice_routes")


def _tool_defs() -> list[Dict[str, Any]]:
    service = get_voice_mcp_service()
    return [
        {
            "name": item.name,
            "description": item.description,
            "inputSchema": item.input_schema,
        }
        for item in service.tool_definitions()
    ]


@router.post("")
async def opencode_mcp_voice(body: JsonRpcRequest):
    started_at = perf_counter()
    params = body.params or {}
    error_code = ""
    if body.method == "initialize":
        response = jsonrpc_response(
            body.id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dawnchat-opencode-voice-mcp", "version": "0.1.0"},
            },
        )
    elif body.method == "tools/list":
        response = jsonrpc_response(body.id, {"tools": _tool_defs()})
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
            service = get_voice_mcp_service()
            result = await service.execute(name, arguments)
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
        "[opencode_mcp_voice] method=%s request_id=%s mcp_name=voice latency_ms=%s error_code=%s",
        body.method,
        body.id,
        int((perf_counter() - started_at) * 1000),
        error_code,
    )
    return response


@router.get("")
async def opencode_mcp_voice_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
