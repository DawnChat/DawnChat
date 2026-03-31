from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..models import PluginInfo
from ..paths import resolve_plugin_frontend_dir, resolve_plugin_source_root


class PluginWebVersionService:
    def __init__(self, get_plugin: Callable[[str], PluginInfo | None]) -> None:
        self._get_plugin = get_plugin

    def get_web_plugin_versions(self, plugin_id: str) -> dict[str, Any]:
        plugin = self._get_plugin(plugin_id)
        if not plugin or not plugin.manifest.plugin_path:
            raise RuntimeError(f"Plugin not found: {plugin_id}")
        if str(plugin.manifest.app_type or "desktop") != "web":
            raise RuntimeError("Only web plugins are supported")

        plugin_root = Path(plugin.manifest.plugin_path)
        source_root = resolve_plugin_source_root(plugin.manifest)
        frontend_dir = resolve_plugin_frontend_dir(plugin.manifest)
        manifest_path = plugin_root / "manifest.json"
        package_path = frontend_dir / "package.json"

        manifest_version = ""
        package_version = ""

        if manifest_path.exists():
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest_version = str(manifest_data.get("version") or "").strip()
        if package_path.exists():
            package_data = json.loads(package_path.read_text(encoding="utf-8"))
            package_version = str(package_data.get("version") or "").strip()

        resolved_version = manifest_version or package_version
        return {
            "manifest_path": str(manifest_path),
            "package_json_path": str(package_path),
            "source_root": str(source_root),
            "frontend_dir": str(frontend_dir),
            "manifest_version": manifest_version,
            "package_version": package_version,
            "resolved_version": resolved_version,
            "version_mismatch": bool(manifest_version and package_version and manifest_version != package_version),
        }

    def sync_web_plugin_versions(self, plugin_id: str, version: str) -> dict[str, Any]:
        normalized_version = str(version or "").strip()
        if not normalized_version:
            raise RuntimeError("version is required")

        plugin = self._get_plugin(plugin_id)
        if not plugin or not plugin.manifest.plugin_path:
            raise RuntimeError(f"Plugin not found: {plugin_id}")
        if str(plugin.manifest.app_type or "desktop") != "web":
            raise RuntimeError("Only web plugins are supported")

        plugin_root = Path(plugin.manifest.plugin_path)
        frontend_dir = resolve_plugin_frontend_dir(plugin.manifest)
        manifest_path = plugin_root / "manifest.json"
        package_path = frontend_dir / "package.json"
        if not manifest_path.exists():
            raise RuntimeError(f"manifest.json not found: {manifest_path}")
        if not package_path.exists():
            raise RuntimeError(f"package.json not found: {package_path}")

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["version"] = normalized_version
        manifest_path.write_text(
            json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        package_data = json.loads(package_path.read_text(encoding="utf-8"))
        package_data["version"] = normalized_version
        package_path.write_text(
            json.dumps(package_data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        plugin.manifest.version = normalized_version
        return self.get_web_plugin_versions(plugin_id)
