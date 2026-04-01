from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Any, Awaitable, Callable

from app.config import Config
from app.utils.logger import get_logger

from ..installer_service import get_plugin_installer_service
from ..market_service import get_plugin_market_service
from ..registry import PluginRegistry
from ..scaffolding import TemplateScaffolderRegistry, TemplateScaffoldRequest
from ..versioning import parse_semver_tuple

logger = get_logger("plugin_template_application_service")


class PluginTemplateApplicationService:
    def __init__(
        self,
        *,
        registry: PluginRegistry,
        template_scaffolders: TemplateScaffolderRegistry,
        suggest_unique_plugin_id: Callable[..., str],
        get_plugin_source_dir: Callable[[str], Path],
        metadata_upsert: Callable[[str, dict[str, Any]], None],
        refresh_registry: Callable[[], Awaitable[None]],
        get_plugin_snapshot: Callable[[str], dict[str, Any] | None],
        prepare_plugin_runtime: Callable[[str], Awaitable[dict[str, Any]]],
    ) -> None:
        self._registry = registry
        self._template_scaffolders = template_scaffolders
        self._suggest_unique_plugin_id = suggest_unique_plugin_id
        self._get_plugin_source_dir = get_plugin_source_dir
        self._metadata_upsert = metadata_upsert
        self._refresh_registry = refresh_registry
        self._get_plugin_snapshot = get_plugin_snapshot
        self._prepare_plugin_runtime = prepare_plugin_runtime

    async def ensure_template_cached(
        self,
        template_id: str,
        *,
        force_refresh: bool = True,
    ) -> dict[str, Any]:
        local_template = self._resolve_local_template_source(template_id)
        market_service = get_plugin_market_service()
        market_plugins = await market_service.list_plugins(force_refresh=force_refresh)
        candidates = [item for item in market_plugins if str(item.get("id") or "") == template_id]
        if not candidates:
            if local_template:
                return local_template
            raise RuntimeError(f"Template not found in market: {template_id}")
        target = max(candidates, key=lambda item: parse_semver_tuple(str(item.get("version") or "0.0.0")))
        version = str(target.get("version") or "")
        
        if local_template:
            local_version = str(local_template.get("version") or "0.0.0")
            if parse_semver_tuple(local_version) >= parse_semver_tuple(version):
                return local_template

        package = target.get("package") or {}
        package_url = str(package.get("url") or "")
        package_sha256 = package.get("sha256")
        if not package_url:
            if local_template:
                return local_template
            raise RuntimeError(f"Template package url missing: {template_id}")
        try:
            cache_payload = await get_plugin_installer_service().cache_template_source(
                template_id=template_id,
                version=version,
                package_url=package_url,
                package_sha256=package_sha256,
            )
        except Exception:
            if local_template:
                logger.warning(
                    "Falling back to bundled template for %s after market cache failure",
                    template_id,
                    exc_info=True,
                )
                return local_template
            raise
        return {
            **cache_payload,
            "template_name": str(target.get("name") or template_id),
            "description": str(target.get("description") or ""),
        }

    async def create_plugin_from_template(
        self,
        *,
        template_id: str,
        app_name: str,
        app_description: str,
        desired_id: str,
        owner_email: str,
        owner_user_id: str,
        app_type: str = "desktop",
    ) -> dict[str, Any]:
        payload = await self.scaffold_plugin_from_template(
            template_id=template_id,
            app_name=app_name,
            app_description=app_description,
            desired_id=desired_id,
            owner_email=owner_email,
            owner_user_id=owner_user_id,
            app_type=app_type,
        )
        await self._prepare_plugin_runtime(payload["plugin_id"])
        await self._refresh_registry()
        payload["plugin"] = self._get_plugin_snapshot(payload["plugin_id"])
        return payload

    async def scaffold_plugin_from_template(
        self,
        *,
        template_id: str,
        app_name: str,
        app_description: str,
        desired_id: str,
        owner_email: str,
        owner_user_id: str,
        app_type: str = "desktop",
    ) -> dict[str, Any]:
        cache = await self.ensure_template_cached(template_id, force_refresh=True)
        template_source = Path(str(cache.get("source_dir") or ""))
        if not template_source.exists():
            raise RuntimeError("Template source cache not found")

        plugin_id = self._suggest_unique_plugin_id(
            desired_id=desired_id,
            owner_email=owner_email,
            owner_user_id=owner_user_id,
        )
        target_dir = self._get_plugin_source_dir(plugin_id)
        if target_dir.exists():
            raise RuntimeError(f"Plugin source already exists: {plugin_id}")
        scaffolder = self._template_scaffolders.get(app_type)
        try:
            await scaffolder.scaffold(
                TemplateScaffoldRequest(
                    template_id=template_id,
                    app_type=app_type,
                    plugin_id=plugin_id,
                    app_name=app_name,
                    app_description=app_description,
                    owner_email=owner_email,
                    owner_user_id=owner_user_id,
                    template_source=template_source,
                    target_dir=target_dir,
                    template_version=str(cache.get("version") or ""),
                )
            )
        except Exception:
            self._rollback_scaffold_target(target_dir)
            raise
        self._metadata_upsert(
            plugin_id,
            {
                "source_type": "user_created",
                "owner_user_id": owner_user_id,
                "owner_email": owner_email,
                "template_id": template_id,
                "created_at": datetime.now().isoformat(),
            },
        )
        await self._refresh_registry()
        return {
            "plugin_id": plugin_id,
            "plugin": self._get_plugin_snapshot(plugin_id),
            "template_version": cache.get("version"),
            "template_id": template_id,
        }

    @staticmethod
    def _rollback_scaffold_target(target_dir: Path) -> None:
        if not target_dir.exists():
            return
        try:
            shutil.rmtree(target_dir)
        except Exception:
            logger.warning("Failed to rollback scaffold target: %s", target_dir, exc_info=True)

    @staticmethod
    def _resolve_local_template_source(template_id: str) -> dict[str, Any] | None:
        official_dir = Config.OFFICIAL_PLUGINS_DIR
        if not official_dir.exists():
            return None
        for item in official_dir.iterdir():
            if not item.is_dir():
                continue
            manifest_path = item / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                data = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if str(data.get("id") or "") != template_id:
                continue
            return {
                "template_id": template_id,
                "version": str(data.get("version") or ""),
                "cached": True,
                "source_dir": str(item),
                "template_name": str(data.get("name") or template_id),
                "description": str(data.get("description") or ""),
                "source": "bundled",
            }
        return None
