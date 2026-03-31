from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from app.services.plugin_mcp_proxy_service import PluginMcpProxyError, get_plugin_mcp_proxy_service


@dataclass(slots=True)
class PluginPythonMcpProxyError(Exception):
    code: str
    message: str


class PluginPythonMcpProxyService:
    async def forward_jsonrpc(self, plugin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await get_plugin_mcp_proxy_service().forward_jsonrpc(
                plugin_id=plugin_id,
                payload=payload,
                endpoint="python_sidecar",
            )
        except PluginMcpProxyError as err:
            raise PluginPythonMcpProxyError(code=err.code, message=err.message) from err


_plugin_python_mcp_proxy_service: PluginPythonMcpProxyService | None = None


def get_plugin_python_mcp_proxy_service() -> PluginPythonMcpProxyService:
    global _plugin_python_mcp_proxy_service
    if _plugin_python_mcp_proxy_service is None:
        _plugin_python_mcp_proxy_service = PluginPythonMcpProxyService()
    return _plugin_python_mcp_proxy_service
