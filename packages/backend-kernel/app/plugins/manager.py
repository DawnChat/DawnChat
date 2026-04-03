"""
DawnChat Plugin System - Plugin Manager

Core plugin lifecycle management: install, start, stop, uninstall.
"""

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import re
import shutil
import sys
from typing import Any, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from fastapi import FastAPI

from app.config import Config
from app.utils.logger import get_logger

from .application.iwp_workspace_application_service import PluginIwpWorkspaceApplicationService
from .application.plugin_agent_attachment_application_service import PluginAgentAttachmentApplicationService
from .application.preview_application_service import PluginPreviewApplicationService
from .application.runtime_application_service import PluginRuntimeApplicationService
from .application.template_application_service import PluginTemplateApplicationService
from .application.web_version_service import PluginWebVersionService
from .env_manager import get_env_manager
from .infrastructure.metadata_repository import PluginMetadataRepository
from .infrastructure.runtime_state_store import PluginRuntimeStateStore
from .inprocess_manager import InProcessPluginManager
from .installer_service import get_plugin_installer_service
from .market_service import get_plugin_market_service
from .models import (
    PluginInfo,
    PluginManifest,
    PluginState,
    build_plugin_workspace_profile,
)
from .preview_manager import PluginPreviewManager
from .registry import PluginRegistry
from .scaffolding import TemplateScaffolderRegistry
from .versioning import is_version_newer, parse_semver_tuple

logger = get_logger("plugin_manager")


class PluginManager:
    """
    Manages plugin lifecycle: discovery, start, stop, and monitoring.
    
    Features:
    - Scans official-plugins directory for built-in plugins
    - Creates isolated venvs using UVEnvManager
    - Starts plugins as subprocesses
    - Tracks plugin state and port allocation
    - Graceful shutdown on application exit
    """
    
    def __init__(self):
        self._registry = PluginRegistry()
        self._env_manager = get_env_manager()
        self._template_scaffolders = TemplateScaffolderRegistry(self._env_manager)
        self._runtime_state_store = PluginRuntimeStateStore()
        self._metadata_repository = PluginMetadataRepository(Config.PLUGIN_METADATA_FILE)
        self._inprocess_manager: Optional[InProcessPluginManager] = None
        self._preview_manager = PluginPreviewManager(self._env_manager)
        self._runtime_service = PluginRuntimeApplicationService(
            self._registry,
            self._env_manager,
            self._preview_manager,
            self._runtime_state_store,
            self._get_inprocess_manager,
            self._is_host_compatible,
        )
        self._iwp_workspace_service = PluginIwpWorkspaceApplicationService(
            get_plugin_path=self.get_plugin_path,
        )
        self._agent_attachment_service = PluginAgentAttachmentApplicationService(
            get_plugin_path=self.get_plugin_path,
            uploads_dir_name=Config.PLUGIN_USER_UPLOADS_DIR_NAME,
            max_bytes=Config.PLUGIN_USER_UPLOAD_MAX_BYTES,
        )
        self._preview_service = PluginPreviewApplicationService(
            self._registry,
            self._preview_manager,
            self.stop_plugin,
            self.has_iwp_requirements,
        )
        self._template_service = PluginTemplateApplicationService(
            registry=self._registry,
            template_scaffolders=self._template_scaffolders,
            suggest_unique_plugin_id=self.suggest_unique_plugin_id,
            get_plugin_source_dir=self._get_plugin_source_dir,
            metadata_upsert=self._upsert_plugin_metadata,
            refresh_registry=self.refresh_registry,
            get_plugin_snapshot=self.get_plugin_snapshot,
            prepare_plugin_runtime=self.prepare_plugin_runtime,
        )
        self._web_version_service = PluginWebVersionService(self.get_plugin)
        self._initialized = False
        self._shutdown_event = asyncio.Event()
        
        logger.info("PluginManager initialized")

    def _upsert_plugin_metadata(self, plugin_id: str, patch: dict[str, Any]) -> None:
        self._metadata_repository.upsert(plugin_id, patch)

    def _remove_plugin_metadata(self, plugin_id: str) -> None:
        self._metadata_repository.remove(plugin_id)

    def update_plugin_publish_metadata(self, plugin_id: str, patch: dict[str, Any]) -> None:
        self._metadata_repository.update_publish(plugin_id, patch)

    def get_plugin_publish_metadata(self, plugin_id: str) -> dict[str, Any]:
        return self._metadata_repository.get_publish(plugin_id)

    def update_plugin_mobile_publish_metadata(self, plugin_id: str, patch: dict[str, Any]) -> None:
        self._metadata_repository.update_mobile_publish(plugin_id, patch)

    def get_plugin_mobile_publish_metadata(self, plugin_id: str) -> dict[str, Any]:
        return self._metadata_repository.get_mobile_publish(plugin_id)

    @staticmethod
    def _normalize_owner_namespace(email: str, user_id: str) -> str:
        email = (email or "").strip().lower()
        local = "user"
        domain_parts: list[str] = ["local"]
        if "@" in email:
            local_raw, domain_raw = email.split("@", 1)
            local = re.sub(r"[^a-z0-9]+", "-", local_raw.strip().lower()).strip("-") or "user"
            domain_parts = [
                re.sub(r"[^a-z0-9]+", "-", part.strip().lower()).strip("-")
                for part in domain_raw.split(".")
                if part.strip()
            ]
            domain_parts = [part for part in domain_parts if part]
            if not domain_parts:
                domain_parts = ["local"]
        user_slug = re.sub(r"[^a-z0-9]+", "-", str(user_id or "").strip().lower()).strip("-")
        user_suffix = user_slug[:12] if user_slug else "uid"
        namespace = ["com", *reversed(domain_parts), local, user_suffix]
        return ".".join(namespace)

    @staticmethod
    def normalize_plugin_id(candidate: str) -> str:
        value = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(candidate or "").strip().lower())
        value = re.sub(r"-{2,}", "-", value).strip(".-_")
        return value

    @classmethod
    def validate_plugin_id(cls, plugin_id: str) -> bool:
        normalized = cls.normalize_plugin_id(plugin_id)
        return bool(re.fullmatch(r"[a-z][a-z0-9._-]{2,127}", normalized)) and normalized == plugin_id

    def suggest_unique_plugin_id(
        self,
        *,
        desired_id: str,
        owner_email: str,
        owner_user_id: str,
    ) -> str:
        desired_slug = self.normalize_plugin_id(desired_id)
        if not desired_slug:
            raise ValueError("Invalid plugin id")
        owner_ns = self._normalize_owner_namespace(owner_email, owner_user_id)
        if desired_slug.startswith("com.") and "." in desired_slug:
            base = desired_slug
        else:
            base = f"{owner_ns}.{desired_slug}"
        candidate = base
        counter = 2
        while self._registry.get(candidate) or self._get_plugin_source_dir(candidate).exists():
            candidate = f"{base}-{counter}"
            counter += 1
        if not self.validate_plugin_id(candidate):
            raise ValueError(f"Invalid generated plugin id: {candidate}")
        return candidate

    def _apply_plugin_metadata_to_registry(self) -> None:
        metadata_map = self._metadata_repository.all()
        for plugin_id, plugin in self._registry.plugins.items():
            metadata = metadata_map.get(plugin_id, {})
            if metadata:
                plugin.source_type = str(metadata.get("source_type") or "unknown")
                plugin.owner_user_id = str(metadata.get("owner_user_id") or "")
                plugin.owner_email = str(metadata.get("owner_email") or "")
                plugin.template_id = str(metadata.get("template_id") or "")
                plugin.created_at = str(metadata.get("created_at") or "")
            elif not plugin.source_type:
                plugin.source_type = "unknown"
    
    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry

    def bind_app(self, app: FastAPI) -> None:
        if self._inprocess_manager is None:
            self._inprocess_manager = InProcessPluginManager(app)

    def _get_inprocess_manager(self) -> Optional[InProcessPluginManager]:
        return self._inprocess_manager
    
    async def initialize(self) -> bool:
        """
        Initialize the plugin manager.
        
        Scans plugin directories and prepares the environment manager.
        """
        if self._initialized:
            return True
        
        try:
            # Initialize environment manager
            if not await self._env_manager.initialize():
                logger.error("Failed to initialize environment manager")
                # Continue anyway - plugins may work without venv in dev mode
            
            # Scan installed plugins from user source directory only.
            user_dir = Config.PLUGIN_SOURCES_DIR
            if user_dir.exists():
                count = self._registry.scan_directory(user_dir, is_official=False)
                logger.info(f"Found {count} user plugins")
            self._apply_plugin_metadata_to_registry()

            self._mark_incompatible_plugins()


            await self._register_plugin_tools()

            self._initialized = True
            logger.info("PluginManager initialization complete")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize PluginManager: {e}", exc_info=True)
            return False

    async def ensure_initialized(self) -> bool:
        if self._initialized:
            return True
        return await self.initialize()

    async def refresh_registry(self) -> None:
        self._registry.clear()
        user_dir = Config.PLUGIN_SOURCES_DIR
        if user_dir.exists():
            self._registry.scan_directory(user_dir, is_official=False)
        self._apply_plugin_metadata_to_registry()
        self._mark_incompatible_plugins()
        await self._register_plugin_tools()

    async def _register_plugin_tools(self) -> None:
        # Legacy host tool registry has been removed. Plugin tool declarations are
        # preserved in manifest metadata and will be bridged by AgentV3 tooling later.
        return

    def _resolve_entry(self, plugin: PluginInfo) -> str:
        if plugin.manifest.capabilities.gradio.enabled:
            return plugin.manifest.capabilities.gradio.entry or "src/main.py"
        if plugin.manifest.capabilities.nicegui.enabled:
            return plugin.manifest.capabilities.nicegui.entry or "src/main.py"
        return "src/main.py"

    @staticmethod
    def _resolve_runtime_backend(plugin: PluginInfo) -> str:
        return PluginRuntimeApplicationService.resolve_runtime_backend(plugin)

    def _resolve_runtime_entry(self, plugin: PluginInfo, plugin_path: Path, backend: str) -> Path:
        return self._runtime_service.resolve_runtime_entry(plugin, plugin_path, backend)

    def _get_plugin_source_dir(self, plugin_id: str) -> Path:
        return Config.PLUGIN_SOURCES_DIR / plugin_id.replace("/", "_").replace(".", "_")

    def _is_host_compatible(self, min_host_version: str) -> bool:
        try:
            return parse_semver_tuple(Config.VERSION) >= parse_semver_tuple(min_host_version)
        except Exception:
            return False

    def _mark_incompatible_plugins(self) -> None:
        for plugin in self._registry.plugins.values():
            if not self._is_host_compatible(plugin.manifest.min_host_version):
                message = f"Host version {Config.VERSION} < required {plugin.manifest.min_host_version}"
                self._registry.update_state(plugin.manifest.id, PluginState.ERROR, message)
                logger.warning(f"Plugin {plugin.manifest.id} incompatible: {message}")

    async def _copy_official_plugins_to_user_dir(self) -> None:
        """
        Copy or symlink official plugins to user directory.
        
        In development mode (DAWNCHAT_DEV_MODE=true):
        - Uses symlinks instead of copying
        - Always updates symlinks to ensure they point to source
        
        In production mode:
        - Copies plugins only if they don't exist
        """
        official_dir = Config.OFFICIAL_PLUGINS_DIR
        user_dir = Config.PLUGIN_DIR
        
        # Check if in development mode
        is_dev_mode = os.getenv("DAWNCHAT_DEV_MODE", "").lower() == "true"
        
        if not official_dir.exists():
            return
            
        if not user_dir.exists():
            try:
                user_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"Failed to create user plugin directory {user_dir}: {e}")
                return
            
        # Iterate official plugins
        try:
            logger.info(f"Checking for official plugins in {official_dir} (dev_mode={is_dev_mode})")
            for item in official_dir.iterdir():
                if not item.is_dir():
                    continue
                    
                manifest_path = item / "manifest.json"
                if not manifest_path.exists():
                    logger.debug(f"Skipping {item.name}: no manifest.json")
                    continue
                    
                try:
                    # Use PluginManifest for validation
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    manifest = PluginManifest(**data)
                    if not self._is_host_compatible(manifest.min_host_version):
                        logger.warning(
                            f"Skipping official plugin {manifest.id}: host {Config.VERSION} < required {manifest.min_host_version}"
                        )
                        continue
                    dest_path = user_dir / item.name
                    
                    if is_dev_mode:
                        # Development mode: use symlinks
                        if dest_path.is_symlink():
                            # Check if symlink points to correct location
                            current_target = dest_path.resolve()
                            if current_target != item.resolve():
                                logger.info(f"Updating symlink for {manifest.id}: {dest_path} -> {item}")
                                dest_path.unlink()
                                dest_path.symlink_to(item)
                            else:
                                logger.debug(f"Symlink for {manifest.id} is up to date")
                        elif dest_path.exists():
                            # Replace existing directory with symlink
                            logger.info(f"Replacing directory with symlink for {manifest.id}: {dest_path}")
                            shutil.rmtree(dest_path)
                            dest_path.symlink_to(item)
                        else:
                            # Create new symlink
                            logger.info(f"Creating symlink for {manifest.id}: {dest_path} -> {item}")
                            dest_path.symlink_to(item)
                    else:
                        # Production mode: copy if not exists
                        if not dest_path.exists():
                            logger.info(f"Importing official plugin {manifest.id} to {dest_path}")
                            shutil.copytree(item, dest_path)
                        else:
                            try:
                                dest_manifest_path = dest_path / "manifest.json"
                                if dest_manifest_path.exists():
                                    src_manifest_text = manifest_path.read_text(encoding="utf-8")
                                    dest_manifest_text = dest_manifest_path.read_text(encoding="utf-8")
                                    if src_manifest_text != dest_manifest_text:
                                        logger.info(f"Updating official plugin {manifest.id} in {dest_path}")
                                        shutil.rmtree(dest_path)
                                        shutil.copytree(item, dest_path)
                                        continue
                            except Exception as e:
                                logger.warning(f"Failed to compare manifests for {manifest.id}: {e}")
                            logger.debug(f"Official plugin {manifest.id} already installed")
                            
                except Exception as e:
                    logger.error(f"Failed to import official plugin from {item}: {e}")
        except Exception as e:
            logger.error(f"Failed to process official plugins directory: {e}")

    async def install_from_package(
        self,
        plugin_id: str,
        version: str,
        package_url: str,
        package_sha256: Optional[str] = None,
        source_type: str = "market_installed",
    ) -> None:
        installer = get_plugin_installer_service()
        await installer.install_or_update(
            plugin_id=plugin_id,
            version=version,
            package_url=package_url,
            package_sha256=package_sha256,
        )
        self._upsert_plugin_metadata(
            plugin_id,
            {
                "source_type": source_type,
                "created_at": datetime.now().isoformat(),
            },
        )

    async def ensure_template_cached(
        self,
        template_id: str,
        *,
        force_refresh: bool = True,
    ) -> dict[str, Any]:
        return await self._template_service.ensure_template_cached(
            template_id,
            force_refresh=force_refresh,
        )

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
        return await self._template_service.create_plugin_from_template(
            template_id=template_id,
            app_name=app_name,
            app_description=app_description,
            desired_id=desired_id,
            owner_email=owner_email,
            owner_user_id=owner_user_id,
            app_type=app_type,
        )

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
        return await self._template_service.scaffold_plugin_from_template(
            template_id=template_id,
            app_name=app_name,
            app_description=app_description,
            desired_id=desired_id,
            owner_email=owner_email,
            owner_user_id=owner_user_id,
            app_type=app_type,
        )

    async def prepare_plugin_runtime(
        self,
        plugin_id: str,
        *,
        include_python: bool = True,
        include_frontend: bool = True,
    ) -> dict[str, Any]:
        return await self._runtime_service.prepare_plugin_runtime(
            plugin_id,
            include_python=include_python,
            include_frontend=include_frontend,
        )

    async def uninstall_plugin_source(self, plugin_id: str) -> bool:
        plugin = self._registry.get(plugin_id)
        if plugin and plugin.state == PluginState.RUNNING:
            await self.stop_plugin(plugin_id)

        source_path = self._get_plugin_source_dir(plugin_id)
        if not source_path.exists():
            if plugin and plugin.manifest.plugin_path:
                source_path = Path(plugin.manifest.plugin_path)

        if not source_path.exists():
            self._registry.unregister(plugin_id)
            return True

        try:
            shutil.rmtree(source_path)
            self._registry.unregister(plugin_id)
            self._remove_plugin_metadata(plugin_id)
            return True
        except Exception as e:
            logger.error("Failed to uninstall plugin source %s: %s", plugin_id, e, exc_info=True)
            return False

    def check_update(self, plugin_id: str, latest_version: str) -> bool:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            return False
        return is_version_newer(latest_version, plugin.manifest.version)

    async def list_market_plugins(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        market_service = get_plugin_market_service()
        market_plugins = await market_service.list_plugins(force_refresh=force_refresh)
        return market_service.merge_with_local(market_plugins, self.list_plugins())
    
    async def start_plugin(self, plugin_id: str) -> Optional[int]:
        return await self._runtime_service.start_plugin(plugin_id)
    
    async def _wait_for_ready(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        timeout: float = 30.0,
        *,
        session_id: str,
    ) -> bool:
        return await self._runtime_service.wait_for_ready(
            plugin_id,
            process,
            timeout=timeout,
            session_id=session_id,
        )
    
    async def _monitor_process(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        *,
        session_id: str,
    ) -> None:
        await self._runtime_service.monitor_process(
            plugin_id,
            process,
            session_id=session_id,
        )
    
    async def stop_plugin(self, plugin_id: str) -> bool:
        return await self._runtime_service.stop_plugin(plugin_id)
    
    async def _cleanup_process(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        port: Optional[int],
    ) -> None:
        await self._runtime_service.cleanup_process(plugin_id, process, port)
    
    async def restart_plugin(self, plugin_id: str) -> Optional[int]:
        return await self._runtime_service.restart_plugin(plugin_id)

    async def start_plugin_preview(self, plugin_id: str) -> Optional[str]:
        return await self._preview_service.start_plugin_preview(plugin_id)

    async def stop_plugin_preview(self, plugin_id: str) -> bool:
        return await self._preview_service.stop_plugin_preview(plugin_id)

    async def retry_plugin_preview_install(self, plugin_id: str) -> bool:
        return await self._preview_service.retry_plugin_preview_install(plugin_id)

    def get_plugin_preview_status(self, plugin_id: str) -> Optional[dict[str, Any]]:
        return self._preview_service.get_plugin_preview_status(plugin_id)

    @staticmethod
    def _resolve_lan_ipv4() -> Optional[str]:
        return PluginPreviewApplicationService._resolve_lan_ipv4()

    def get_mobile_preview_share_url(self, plugin_id: str) -> dict[str, str]:
        return self._preview_service.get_mobile_preview_share_url(plugin_id)

    def resolve_mcp_endpoint(self, plugin_id: str) -> Optional[dict[str, Any]]:
        return self._preview_service.resolve_mcp_endpoint(plugin_id)

    def resolve_mcp_endpoints(self, plugin_id: str) -> Optional[dict[str, Any]]:
        return self._preview_service.resolve_mcp_endpoints(plugin_id)

    def get_plugin_runtime_info(self, plugin_id: str) -> Optional[dict[str, Any]]:
        return self._preview_service.get_plugin_runtime_info(plugin_id)
    
    async def shutdown(self) -> None:
        """Stop all running plugins and clean up."""
        logger.info("Shutting down PluginManager...")
        
        # Stop all running plugins
        running_plugins = self._registry.list_by_state(PluginState.RUNNING)
        for plugin in running_plugins:
            await self.stop_plugin(plugin.manifest.id)
        await self._preview_manager.shutdown(self._registry.plugins)
        
        self._shutdown_event.set()
        logger.info("PluginManager shutdown complete")
    
    def list_plugins(self) -> list[dict[str, Any]]:
        """List all plugins."""
        return self._registry.list_all()
    
    def get_plugin(self, plugin_id: str) -> Optional[PluginInfo]:
        """Get the canonical plugin domain model."""
        return self._registry.get(plugin_id)

    def get_plugin_snapshot(self, plugin_id: str) -> Optional[dict[str, Any]]:
        """Get a serialized plugin snapshot for API responses."""
        plugin = self.get_plugin(plugin_id)
        if plugin:
            return plugin.to_dict()
        return None

    def get_plugin_workspace_profile(self, plugin_id: str) -> Optional[dict[str, Any]]:
        """Build a coding-agent workspace profile for a plugin."""
        plugin = self.get_plugin(plugin_id)
        if plugin is None:
            return None
        return build_plugin_workspace_profile(plugin)

    def get_plugin_path(self, plugin_id: str) -> Optional[str]:
        """Get plugin source path."""
        plugin = self.get_plugin(plugin_id)
        if not plugin or not plugin.manifest.plugin_path:
            return None
        return str(plugin.manifest.plugin_path)

    def update_plugin_display_name(self, plugin_id: str, name: str) -> dict[str, Any]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            raise FileNotFoundError(f"Plugin not found: {plugin_id}")
        if plugin.manifest.is_official:
            raise RuntimeError("Official plugin display name cannot be modified")

        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("Plugin name cannot be empty")

        plugin_path = str(plugin.manifest.plugin_path or "").strip()
        if not plugin_path:
            raise RuntimeError(f"Plugin source path not found: {plugin_id}")
        manifest_path = Path(plugin_path) / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Plugin manifest not found: {plugin_id}")

        try:
            manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Failed to load plugin manifest: {plugin_id}") from exc
        if not isinstance(manifest_payload, dict):
            raise RuntimeError(f"Invalid plugin manifest format: {plugin_id}")

        manifest_payload["name"] = normalized_name
        try:
            manifest_path.write_text(
                json.dumps(manifest_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to save plugin manifest: {plugin_id}") from exc

        plugin.manifest.name = normalized_name
        return {"plugin_id": plugin_id, "name": normalized_name}

    def get_web_plugin_versions(self, plugin_id: str) -> dict[str, Any]:
        return self._web_version_service.get_web_plugin_versions(plugin_id)

    def sync_web_plugin_versions(self, plugin_id: str, version: str) -> dict[str, Any]:
        return self._web_version_service.sync_web_plugin_versions(plugin_id, version)

    def list_iwp_markdown_files(self, plugin_id: str) -> dict[str, Any]:
        return self._iwp_workspace_service.list_markdown_files(plugin_id)

    def has_iwp_requirements(self, plugin_id: str) -> bool:
        return self._iwp_workspace_service.has_iwp_requirements(plugin_id)

    def read_iwp_markdown_file(self, plugin_id: str, relative_path: str) -> dict[str, Any]:
        return self._iwp_workspace_service.read_markdown_file(plugin_id, relative_path)

    def save_iwp_markdown_file(
        self,
        plugin_id: str,
        relative_path: str,
        content: str,
        expected_hash: str = "",
    ) -> dict[str, Any]:
        return self._iwp_workspace_service.save_markdown_file(
            plugin_id=plugin_id,
            relative_path=relative_path,
            content=content,
            expected_hash=expected_hash,
        )

    async def start_iwp_build(self, plugin_id: str) -> str:
        return await self._iwp_workspace_service.start_build(plugin_id)

    async def get_iwp_build_task(self, task_id: str) -> dict[str, Any] | None:
        return await self._iwp_workspace_service.get_build_task(task_id)

    async def save_agent_attachment(self, plugin_id: str, file: Any) -> dict[str, Any]:
        return await self._agent_attachment_service.save_upload(plugin_id, file)

    def get_plugin_detail_metadata(self, plugin_id: str) -> dict[str, Any]:
        """Read key metadata from manifest.json and pyproject.toml for UI detail dialog."""
        plugin = self._registry.get(plugin_id)
        if not plugin or not plugin.manifest.plugin_path:
            return {}

        plugin_root = Path(plugin.manifest.plugin_path)
        manifest_path = plugin_root / "manifest.json"
        pyproject_path = plugin_root / "pyproject.toml"

        detail: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
                ui_cfg = manifest_data.get("ui") or {}
                detail["manifest"] = {
                    "id": manifest_data.get("id"),
                    "name": manifest_data.get("name"),
                    "version": manifest_data.get("version"),
                    "description": manifest_data.get("description"),
                    "author": manifest_data.get("author"),
                    "framework": ui_cfg.get("framework"),
                    "entry": ui_cfg.get("entry"),
                    "tags": manifest_data.get("tags") or [],
                }
                detail["web_publish"] = self.get_plugin_publish_metadata(plugin_id)
            except Exception as e:
                logger.warning("Failed to read manifest detail for %s: %s", plugin_id, e)

        if pyproject_path.exists():
            try:
                pyproject_data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
                project_cfg = pyproject_data.get("project") or {}
                detail["pyproject"] = {
                    "name": project_cfg.get("name"),
                    "version": project_cfg.get("version"),
                    "description": project_cfg.get("description"),
                    "requires_python": project_cfg.get("requires-python"),
                    "dependencies": project_cfg.get("dependencies") or [],
                }
            except Exception as e:
                logger.warning("Failed to read pyproject detail for %s: %s", plugin_id, e)

        return detail


# Singleton instance
_plugin_manager: Optional[PluginManager] = None


def get_plugin_manager() -> PluginManager:
    """Get the global PluginManager instance."""
    global _plugin_manager
    if _plugin_manager is None:
        _plugin_manager = PluginManager()
    return _plugin_manager
