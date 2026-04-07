from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, Dict, Iterable, Protocol

from app.api.opencode_mcp_common import (
    JsonRpcRequest,
    jsonrpc_error_from_internal,
    jsonrpc_invalid_params,
    jsonrpc_method_not_found,
    jsonrpc_response,
    to_mcp_tool_result,
)
from app.utils.logger import get_logger


class OpencodeMcpService(Protocol):
    def tool_definitions(self) -> Iterable[Any]:
        ...

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        ...


class OpencodeJsonRpcProxy(Protocol):
    async def forward_jsonrpc(self, payload: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class OpenCodeMcpHubConfig:
    mcp_name: str
    server_name: str
    server_version: str = "0.1.0"
    mode: str = "tool_service"
    proxy_allowed_methods: tuple[str, ...] = ("tools/list", "tools/call")


class OpenCodeMcpHub:
    """
    Unified JSON-RPC handler for OpenCode MCP routes.

    Integration guide:
    - tool_service mode: provide service_factory() with tool_definitions()/execute().
    - jsonrpc_proxy mode: provide proxy_factory() with forward_jsonrpc(payload, context).
    """

    def __init__(
        self,
        config: OpenCodeMcpHubConfig,
        service_factory: Callable[[], OpencodeMcpService] | None = None,
        proxy_factory: Callable[[], OpencodeJsonRpcProxy] | None = None,
        proxy_error_mapper: Callable[[Exception], tuple[str, str]] | None = None,
    ) -> None:
        self._config = config
        self._service_factory = service_factory
        self._proxy_factory = proxy_factory
        self._proxy_error_mapper = proxy_error_mapper or self._default_proxy_error_mapper
        self._logger = get_logger(f"opencode_mcp_{config.mcp_name}_hub")

    async def handle(self, body: JsonRpcRequest, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        started_at = perf_counter()
        request_context = context or {}
        params = body.params or {}
        error_code = ""
        if body.method == "initialize":
            response = jsonrpc_response(
                body.id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": self._config.server_name,
                        "version": self._config.server_version,
                    },
                },
            )
        elif self._config.mode == "tool_service":
            if body.method == "tools/list":
                response = jsonrpc_response(body.id, {"tools": self._tool_defs()})
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
                    service = self._require_service_factory()()
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
        elif self._config.mode == "jsonrpc_proxy":
            if body.method not in set(self._config.proxy_allowed_methods):
                error_code = "method_not_found"
                response = jsonrpc_method_not_found(body.id, body.method)
            else:
                try:
                    proxy = self._require_proxy_factory()()
                    payload = body.model_dump(mode="python", exclude_none=True)
                    response = await proxy.forward_jsonrpc(payload=payload, context=request_context)
                except Exception as err:
                    mapped_code, mapped_message = self._proxy_error_mapper(err)
                    error_code = mapped_code
                    response = jsonrpc_error_from_internal(body.id, mapped_code, mapped_message)
        else:
            error_code = "hub_mode_not_supported"
            response = jsonrpc_error_from_internal(
                body.id,
                "hub_mode_not_supported",
                f"unsupported hub mode: {self._config.mode}",
            )
        self._logger.info(
            "[opencode_mcp_hub] method=%s request_id=%s mcp_name=%s latency_ms=%s error_code=%s",
            body.method,
            body.id,
            self._config.mcp_name,
            int((perf_counter() - started_at) * 1000),
            error_code,
        )
        return response

    def _tool_defs(self) -> list[Dict[str, Any]]:
        service = self._require_service_factory()()
        return [self._normalize_tool_def(item) for item in service.tool_definitions()]

    def _require_service_factory(self) -> Callable[[], OpencodeMcpService]:
        if self._service_factory is None:
            raise RuntimeError("OpenCodeMcpHub requires service_factory for tool_service mode")
        return self._service_factory

    def _require_proxy_factory(self) -> Callable[[], OpencodeJsonRpcProxy]:
        if self._proxy_factory is None:
            raise RuntimeError("OpenCodeMcpHub requires proxy_factory for jsonrpc_proxy mode")
        return self._proxy_factory

    @staticmethod
    def _normalize_tool_def(item: Any) -> Dict[str, Any]:
        if isinstance(item, dict):
            input_schema = item.get("inputSchema")
            if input_schema is None:
                input_schema = item.get("input_schema")
            return {
                "name": str(item.get("name") or ""),
                "description": str(item.get("description") or ""),
                "inputSchema": input_schema if isinstance(input_schema, dict) else {"type": "object"},
            }
        name = str(getattr(item, "name", "") or "")
        description = str(getattr(item, "description", "") or "")
        input_schema = getattr(item, "input_schema", None)
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object"}
        return {
            "name": name,
            "description": description,
            "inputSchema": input_schema,
        }

    @staticmethod
    def _default_proxy_error_mapper(err: Exception) -> tuple[str, str]:
        return ("proxy_forward_failed", str(err))
