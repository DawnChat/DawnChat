from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import BaseModel


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: Dict[str, Any] | None = None


def jsonrpc_response(request_id: int | str | None, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(
    request_id: int | str | None,
    code: int,
    message: str,
    data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"code": code, "message": message}
    if isinstance(data, dict) and data:
        payload["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": payload}


def jsonrpc_method_not_found(request_id: int | str | None, method: str) -> Dict[str, Any]:
    return jsonrpc_error(request_id, -32601, f"method not found: {method}")


def jsonrpc_invalid_params(request_id: int | str | None, message: str) -> Dict[str, Any]:
    return jsonrpc_error(request_id, -32602, message)


def jsonrpc_error_from_internal(
    request_id: int | str | None,
    internal_code: str,
    message: str,
    data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized = str(internal_code or "").strip().lower()
    if normalized in {"invalid_arguments", "invalid_params"}:
        code = -32602
    elif normalized in {"method_not_found", "not_found"}:
        code = -32601
    else:
        code = -32000
    merged_data = {"error_code": internal_code}
    if isinstance(data, dict):
        merged_data.update(data)
    return jsonrpc_error(request_id, code, message, merged_data)


def to_mcp_tool_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    ok = bool(payload.get("ok", True))
    text = json.dumps(payload, ensure_ascii=False)
    return {"content": [{"type": "text", "text": text}], "isError": not ok}
