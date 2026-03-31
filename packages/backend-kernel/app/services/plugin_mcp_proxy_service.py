from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Dict, Literal

import httpx

from app.config import Config
from app.plugins import get_plugin_manager
from app.services.plugin_id_resolver import PluginIdResolveError, get_plugin_id_resolver
from app.utils.logger import get_logger

EndpointKind = Literal["backend", "python_sidecar"]


@dataclass(slots=True)
class PluginMcpProxyError(Exception):
    code: str
    message: str
    details: Dict[str, Any] | None = None


class PluginMcpProxyService:
    def __init__(self) -> None:
        timeout = httpx.Timeout(
            connect=Config.MCP_PROXY_TIMEOUT_CONNECT_SECONDS,
            read=Config.MCP_PROXY_TIMEOUT_READ_SECONDS,
            write=Config.MCP_PROXY_TIMEOUT_WRITE_SECONDS,
            pool=Config.MCP_PROXY_TIMEOUT_POOL_SECONDS,
        )
        self._client = httpx.AsyncClient(timeout=timeout, trust_env=False)
        self._logger = get_logger("plugin_mcp_proxy_service")

    async def forward_jsonrpc(self, plugin_id: str, payload: Dict[str, Any], endpoint: EndpointKind) -> Dict[str, Any]:
        started_at = perf_counter()
        raw_plugin_id = str(plugin_id or "").strip()
        resolved_plugin_id = raw_plugin_id
        resolve_source = ""
        request_id = payload.get("id")
        method = str(payload.get("method") or "")
        try:
            resolved = self._resolve_canonical_plugin_id(raw_plugin_id)
            resolved_plugin_id = resolved.get("plugin_id", raw_plugin_id)
            resolve_source = resolved.get("resolve_source", "")
        except PluginMcpProxyError as err:
            self._log_failure(
                endpoint=endpoint,
                plugin_id=resolved_plugin_id,
                raw_plugin_id=raw_plugin_id,
                resolve_source=resolve_source,
                method=method,
                request_id=request_id,
                latency_ms=int((perf_counter() - started_at) * 1000),
                error=err,
            )
            raise
        endpoint_payload = self._resolve_endpoint(resolved_plugin_id, endpoint)
        port = self._parse_port(endpoint_payload.get("port"))
        source = str(endpoint_payload.get("source") or "")
        target_url = f"http://127.0.0.1:{port}/mcp"
        try:
            response = await self._client.post(target_url, json=payload)
        except Exception as err:
            error = PluginMcpProxyError(
                code=self._code(endpoint, "request_failed"),
                message=f"failed to reach plugin {self._channel(endpoint)} mcp: {err}",
            )
            self._log_failure(
                endpoint=endpoint,
                plugin_id=resolved_plugin_id,
                raw_plugin_id=raw_plugin_id,
                resolve_source=resolve_source,
                method=method,
                request_id=request_id,
                latency_ms=int((perf_counter() - started_at) * 1000),
                error=error,
            )
            raise error from err
        if response.status_code >= 400:
            error = PluginMcpProxyError(
                code=self._code(endpoint, "http_error"),
                message=f"plugin {self._channel(endpoint)} mcp http {response.status_code}",
                details={"status_code": response.status_code},
            )
            self._log_failure(
                endpoint=endpoint,
                plugin_id=resolved_plugin_id,
                raw_plugin_id=raw_plugin_id,
                resolve_source=resolve_source,
                method=method,
                request_id=request_id,
                latency_ms=int((perf_counter() - started_at) * 1000),
                error=error,
            )
            raise error
        try:
            decoded = response.json()
        except ValueError as err:
            error = PluginMcpProxyError(
                code=self._code(endpoint, "invalid_json"),
                message=f"plugin {self._channel(endpoint)} mcp returned invalid json",
            )
            self._log_failure(
                endpoint=endpoint,
                plugin_id=resolved_plugin_id,
                raw_plugin_id=raw_plugin_id,
                resolve_source=resolve_source,
                method=method,
                request_id=request_id,
                latency_ms=int((perf_counter() - started_at) * 1000),
                error=error,
            )
            raise error from err
        if not isinstance(decoded, dict):
            error = PluginMcpProxyError(
                code=self._code(endpoint, "invalid_payload"),
                message=f"plugin {self._channel(endpoint)} mcp returned non-object payload",
            )
            self._log_failure(
                endpoint=endpoint,
                plugin_id=resolved_plugin_id,
                raw_plugin_id=raw_plugin_id,
                resolve_source=resolve_source,
                method=method,
                request_id=request_id,
                latency_ms=int((perf_counter() - started_at) * 1000),
                error=error,
            )
            raise error
        self._logger.info(
            "[plugin_mcp_proxy] mcp_name=%s plugin_id=%s raw_plugin_id=%s resolve_source=%s request_id=%s method=%s source=%s latency_ms=%s error_code=",
            self._mcp_name(endpoint),
            resolved_plugin_id,
            raw_plugin_id,
            resolve_source,
            request_id,
            method,
            source,
            int((perf_counter() - started_at) * 1000),
        )
        return decoded

    @staticmethod
    def _resolve_canonical_plugin_id(raw_plugin_id: str) -> Dict[str, str]:
        try:
            resolved = get_plugin_id_resolver().resolve(raw_plugin_id)
        except PluginIdResolveError as err:
            raise PluginMcpProxyError(code=err.code, message=err.message, details=err.details) from err
        return {
            "plugin_id": resolved.canonical_plugin_id,
            "resolve_source": resolved.resolve_source,
        }

    def _resolve_endpoint(self, plugin_id: str, endpoint: EndpointKind) -> Dict[str, Any]:
        manager = get_plugin_manager()
        if manager.get_plugin_snapshot(plugin_id) is None:
            raise PluginMcpProxyError(
                code="plugin_not_found",
                message=f"plugin not found: {plugin_id}",
            )
        if endpoint == "backend":
            payload = manager.resolve_mcp_endpoint(plugin_id)
            payload_dict = payload if isinstance(payload, dict) else {}
            port = self._parse_port(payload_dict.get("port"))
            if port <= 0:
                raise PluginMcpProxyError(
                    code=self._code(endpoint, "unavailable"),
                    message=f"plugin backend endpoint unavailable: {plugin_id}",
                )
            return {"port": port, "source": str(payload_dict.get("source") or "")}
        payloads = manager.resolve_mcp_endpoints(plugin_id) or {}
        payload = payloads.get("python_sidecar") if isinstance(payloads, dict) else None
        payload_dict = payload if isinstance(payload, dict) else {}
        port = self._parse_port(payload_dict.get("port"))
        if port <= 0:
            raise PluginMcpProxyError(
                code=self._code(endpoint, "unavailable"),
                message=f"plugin python endpoint unavailable: {plugin_id}",
            )
        return {"port": port, "source": str(payload_dict.get("source") or "")}

    @staticmethod
    def _parse_port(raw: Any) -> int:
        if raw is None or isinstance(raw, bool):
            return 0
        if isinstance(raw, (int, float, str)):
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
        return 0

    def _log_failure(
        self,
        endpoint: EndpointKind,
        plugin_id: str,
        raw_plugin_id: str,
        resolve_source: str,
        method: str,
        request_id: Any,
        latency_ms: int,
        error: PluginMcpProxyError,
    ) -> None:
        self._logger.info(
            "[plugin_mcp_proxy] mcp_name=%s plugin_id=%s raw_plugin_id=%s resolve_source=%s request_id=%s method=%s latency_ms=%s error_code=%s",
            self._mcp_name(endpoint),
            plugin_id,
            raw_plugin_id,
            resolve_source,
            request_id,
            method,
            latency_ms,
            error.code,
        )

    @staticmethod
    def _mcp_name(endpoint: EndpointKind) -> str:
        return "plugin_backend" if endpoint == "backend" else "plugin_python"

    @staticmethod
    def _channel(endpoint: EndpointKind) -> str:
        return "backend" if endpoint == "backend" else "python"

    def _code(self, endpoint: EndpointKind, suffix: str) -> str:
        prefix = "plugin_backend" if endpoint == "backend" else "plugin_python"
        return f"{prefix}_{suffix}"


_plugin_mcp_proxy_service: PluginMcpProxyService | None = None


def get_plugin_mcp_proxy_service() -> PluginMcpProxyService:
    global _plugin_mcp_proxy_service
    if _plugin_mcp_proxy_service is None:
        _plugin_mcp_proxy_service = PluginMcpProxyService()
    return _plugin_mcp_proxy_service
