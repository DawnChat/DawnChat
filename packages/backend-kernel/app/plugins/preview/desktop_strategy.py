from __future__ import annotations

from typing import TYPE_CHECKING

from app.plugins.paths import resolve_plugin_source_root

from .base import PreviewSession, PreviewStrategy

if TYPE_CHECKING:
    from app.plugins.preview_manager import PluginPreviewManager


class DesktopPreviewStrategy(PreviewStrategy):
    @property
    def app_type(self) -> str:
        return "desktop"

    async def create_session(self, manager: PluginPreviewManager, plugin) -> PreviewSession:
        if not plugin.manifest.plugin_path:
            raise RuntimeError("Plugin path missing")
        source_root = resolve_plugin_source_root(plugin.manifest)
        backend_kind = manager.resolve_preview_backend(plugin)
        entry_path = manager.resolve_preview_entry_path(plugin, source_root, backend_kind)
        python_sidecar_entry_path = manager.resolve_python_sidecar_entry_path(plugin, source_root)
        frontend_port = manager.allocate_port()
        backend_port = manager.allocate_port()
        python_exe = await manager.resolve_python_executable(plugin) if backend_kind == "python" else None
        python_sidecar_port = manager.allocate_port() if python_sidecar_entry_path else None
        python_sidecar_exe = (
            await manager.resolve_python_sidecar_executable(plugin, source_root, python_sidecar_entry_path)
            if python_sidecar_entry_path
            else None
        )
        deps_ready = manager.are_preview_frontend_deps_ready(plugin)
        # deps not ready -> start with dist URL, then async install and auto switch to dev URL.
        frontend_mode = "dev" if deps_ready else "dist"
        install_status = "success" if deps_ready else "running"
        return PreviewSession(
            plugin_id=plugin.manifest.id,
            app_type=self.app_type,
            plugin_path=source_root,
            backend_kind=backend_kind,
            entry_path=entry_path,
            frontend_port=frontend_port,
            backend_port=backend_port,
            python_exe=python_exe,
            python_sidecar_entry_path=python_sidecar_entry_path,
            python_sidecar_exe=python_sidecar_exe,
            python_sidecar_port=python_sidecar_port,
            deps_ready=deps_ready,
            frontend_mode=frontend_mode,
            install_status=install_status,
        )

    async def start(self, manager: PluginPreviewManager, plugin, session: PreviewSession) -> None:
        await manager.start_backend_process(plugin, session)
        if session.deps_ready:
            await manager.start_bun_process(plugin, session)
        else:
            manager.schedule_preview_frontend_install(plugin, session)
        await manager.start_watcher(plugin, session)

    def build_url(self, bind_host: str, session: PreviewSession) -> str | None:
        if session.frontend_mode == "dev" and session.frontend_port:
            return f"http://{bind_host}:{session.frontend_port}/"
        if session.backend_port:
            return f"http://{bind_host}:{session.backend_port}/"
        return None
