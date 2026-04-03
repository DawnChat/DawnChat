from __future__ import annotations

import ipaddress
import socket
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlparse, urlunparse

from app.config import Config
from app.voice import get_tts_runtime_service

from ..models import PluginPreviewState, PluginState
from ..preview_manager import PluginPreviewManager
from ..registry import PluginRegistry


class PluginPreviewApplicationService:
    def __init__(
        self,
        registry: PluginRegistry,
        preview_manager: PluginPreviewManager,
        stop_runtime: Callable[[str], Awaitable[bool]],
        has_iwp_requirements: Callable[[str], bool] | None = None,
    ) -> None:
        self._registry = registry
        self._preview_manager = preview_manager
        self._stop_runtime = stop_runtime
        self._has_iwp_requirements = has_iwp_requirements or (lambda _plugin_id: False)

    async def start_plugin_preview(self, plugin_id: str) -> Optional[str]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return None
        if plugin.state == PluginState.RUNNING:
            await self._stop_runtime(plugin_id)
        ok = await self._preview_manager.start_preview(plugin)
        if not ok:
            return None
        return plugin.preview.url

    async def stop_plugin_preview(self, plugin_id: str) -> bool:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return False
        return await self._preview_manager.stop_preview(plugin)

    async def retry_plugin_preview_install(self, plugin_id: str) -> bool:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return False
        return await self._preview_manager.retry_preview_frontend_install(plugin)

    def get_plugin_preview_status(self, plugin_id: str) -> Optional[dict[str, Any]]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return None
        return {
            "state": plugin.preview.state.value,
            "url": plugin.preview.url,
            "backend_port": plugin.preview.backend_port,
            "frontend_port": plugin.preview.frontend_port,
            "log_session_id": plugin.preview.log_session_id,
            "error_message": plugin.preview.error_message,
            "frontend_mode": plugin.preview.frontend_mode,
            "deps_ready": plugin.preview.deps_ready,
            "frontend_reachable": plugin.preview.frontend_reachable,
            "frontend_last_probe_at": plugin.preview.frontend_last_probe_at,
            "install_status": plugin.preview.install_status,
            "install_error_message": plugin.preview.install_error_message,
            "python_sidecar_port": plugin.preview.python_sidecar_port,
            "python_sidecar_state": plugin.preview.python_sidecar_state,
            "python_sidecar_error_message": plugin.preview.python_sidecar_error_message,
            "workbench_layout": str(getattr(getattr(plugin.manifest, "preview", None), "workbench_layout", "default") or "default"),
            "has_iwp_requirements": self._has_iwp_requirements(plugin_id),
        }

    @staticmethod
    def _resolve_lan_ipv4() -> Optional[str]:
        candidates: list[str] = []
        for remote in (("8.8.8.8", 80), ("1.1.1.1", 80)):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    sock.connect(remote)
                    ip = str(sock.getsockname()[0] or "").strip()
                    if ip:
                        candidates.append(ip)
            except Exception:
                continue

        try:
            infos = socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
            for info in infos:
                ip = str(info[4][0] or "").strip()
                if ip:
                    candidates.append(ip)
        except Exception:
            pass

        for ip in candidates:
            try:
                addr = ipaddress.ip_address(ip)
            except ValueError:
                continue
            if addr.version != 4:
                continue
            if addr.is_loopback or addr.is_link_local:
                continue
            if addr.is_private:
                return ip
        return None

    def get_mobile_preview_share_url(self, plugin_id: str) -> dict[str, str]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            raise RuntimeError(f"Plugin not found: {plugin_id}")
        if str(plugin.manifest.app_type or "desktop") != "mobile":
            raise RuntimeError("Only mobile plugins are supported")
        if plugin.preview.state != PluginPreviewState.RUNNING or not plugin.preview.url:
            raise RuntimeError("Plugin preview is not running")

        preview_url = str(plugin.preview.url).strip()
        parsed = urlparse(preview_url)
        host = str(parsed.hostname or "").strip().lower()
        if not host:
            raise RuntimeError("Invalid preview url")

        if host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
            lan_ip = self._resolve_lan_ipv4()
            if not lan_ip:
                raise RuntimeError("Unable to resolve LAN IPv4 address")
            netloc = f"{lan_ip}:{parsed.port}" if parsed.port else lan_ip
            share_url = urlunparse(
                (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
            )
            return {"share_url": share_url, "lan_ip": lan_ip}

        return {"share_url": preview_url, "lan_ip": host}

    def resolve_mcp_endpoint(self, plugin_id: str) -> Optional[dict[str, Any]]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return None
        if plugin.preview.state == PluginPreviewState.RUNNING and plugin.preview.backend_port:
            return {"port": plugin.preview.backend_port, "source": "preview"}
        if plugin.state == PluginState.RUNNING and plugin.runtime.port:
            return {"port": plugin.runtime.port, "source": "runtime"}
        return None

    def resolve_mcp_endpoints(self, plugin_id: str) -> Optional[dict[str, Any]]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return None
        backend_endpoint = self.resolve_mcp_endpoint(plugin_id)
        python_endpoint = None
        if (
            plugin.preview.state == PluginPreviewState.RUNNING
            and plugin.preview.python_sidecar_state == "running"
            and plugin.preview.python_sidecar_port
        ):
            python_endpoint = {"port": plugin.preview.python_sidecar_port, "source": "preview_python_sidecar"}
        return {
            "backend": backend_endpoint,
            "python_sidecar": python_endpoint,
        }

    def get_plugin_runtime_info(self, plugin_id: str) -> Optional[dict[str, Any]]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return None
        endpoint = self.resolve_mcp_endpoint(plugin_id)
        endpoints = self.resolve_mcp_endpoints(plugin_id) or {"backend": endpoint, "python_sidecar": None}
        bun_binary = Config.get_bun_binary()
        uv_binary = Config.get_uv_binary()
        pbs_python = Config.get_pbs_python()
        python_sidecar_state = str(plugin.preview.python_sidecar_state or "stopped")
        python_sidecar_running = bool(
            python_sidecar_state == "running"
            and plugin.preview.python_sidecar_port
            and plugin.preview.state == PluginPreviewState.RUNNING
        )
        return {
            "plugin_id": plugin_id,
            "app_type": str(plugin.manifest.app_type or "desktop"),
            "preview": self.get_plugin_preview_status(plugin_id),
            "runtime": {
                "state": plugin.state.value,
                "port": plugin.runtime.port,
                "gradio_url": plugin.runtime.gradio_url,
            },
            "mcp_endpoint": endpoint,
            "mcp_endpoints": endpoints,
            "python_sidecar": {
                "state": python_sidecar_state,
                "running": python_sidecar_running,
                "port": plugin.preview.python_sidecar_port,
                "error_message": plugin.preview.python_sidecar_error_message,
                "endpoint": endpoints.get("python_sidecar"),
            },
            "environment": {
                "bun_binary": str(bun_binary) if bun_binary else "",
                "bun_binary_exists": bool(bun_binary and bun_binary.exists()),
                "python": {
                    "status": "running" if python_sidecar_running else "available" if pbs_python else "unavailable",
                    "available": bool(pbs_python and pbs_python.exists()),
                    "sidecar_running": python_sidecar_running,
                    "sidecar_port": plugin.preview.python_sidecar_port,
                    "sidecar_error_message": plugin.preview.python_sidecar_error_message,
                    "pbs_python": str(pbs_python) if pbs_python else "",
                    "pbs_python_exists": bool(pbs_python and pbs_python.exists()),
                    "uv_binary": str(uv_binary) if uv_binary else "",
                    "uv_binary_exists": bool(uv_binary and uv_binary.exists()),
                },
            },
            "tts": get_tts_runtime_service().get_plugin_runtime_state(plugin_id),
        }
