from __future__ import annotations

from typing import TYPE_CHECKING

from app.plugins.paths import resolve_plugin_frontend_dir, resolve_plugin_source_root

from .base import PreviewSession, PreviewStrategy

if TYPE_CHECKING:
    from app.plugins.preview_manager import PluginPreviewManager


class WebPreviewStrategy(PreviewStrategy):
    @property
    def app_type(self) -> str:
        return "web"

    async def create_session(self, manager: PluginPreviewManager, plugin) -> PreviewSession:
        if not plugin.manifest.plugin_path:
            raise RuntimeError("Plugin path missing")
        source_root = resolve_plugin_source_root(plugin.manifest)
        web_src = resolve_plugin_frontend_dir(plugin.manifest)
        if not web_src.exists():
            raise RuntimeError(f"Web source directory missing: {web_src}")
        frontend_port = manager.allocate_port()
        return PreviewSession(
            plugin_id=plugin.manifest.id,
            app_type=self.app_type,
            plugin_path=source_root,
            frontend_port=frontend_port,
        )

    async def start(self, manager: PluginPreviewManager, plugin, session: PreviewSession) -> None:
        await manager.start_bun_process(plugin, session)
