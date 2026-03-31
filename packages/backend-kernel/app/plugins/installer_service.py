"""
Plugin installer service.

Handles package download, integrity verification, extraction and dependency setup.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any, Optional
from zipfile import ZipFile

from app.config import Config
from app.services.downloaders import DownloadProgress, DownloadRequest, get_download_router
from app.utils.logger import get_logger

from .env_manager import get_env_manager
from .env_policy import resolve_plugin_env
from .models import PluginManifest

logger = get_logger("plugin_installer_service")


class PluginInstallerService:
    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._running_jobs: dict[str, asyncio.Task[Any]] = {}
        self._lock = asyncio.Lock()
        self._state_file = Config.PLUGIN_DOWNLOAD_DIR / "install_tasks.json"
        self._load_state()

    def _load_state(self) -> None:
        if not self._state_file.exists():
            return
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._tasks = data
        except Exception:
            self._tasks = {}

    def _save_state(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(
                json.dumps(self._tasks, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to persist installer state: %s", e)

    def _set_task(
        self,
        plugin_id: str,
        *,
        status: str,
        message: str,
        progress: int,
        error: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        task = self._tasks.get(plugin_id, {})
        task.update(
            {
                "plugin_id": plugin_id,
                "version": version or task.get("version"),
                "status": status,
                "message": message,
                "progress": progress,
                "error": error,
            }
        )
        self._tasks[plugin_id] = task
        self._save_state()

    def get_progress(self, plugin_id: str) -> dict[str, Any]:
        return self._tasks.get(
            plugin_id,
            {
                "plugin_id": plugin_id,
                "status": "idle",
                "progress": 0,
                "message": "",
                "error": None,
            },
        )

    async def install_or_update(
        self,
        *,
        plugin_id: str,
        version: str,
        package_url: str,
        package_sha256: Optional[str] = None,
    ) -> None:
        async with self._lock:
            running = self._running_jobs.get(plugin_id)
            if running and not running.done():
                return
            job = asyncio.create_task(
                self._run_install(
                    plugin_id=plugin_id,
                    version=version,
                    package_url=package_url,
                    package_sha256=package_sha256,
                )
            )
            self._running_jobs[plugin_id] = job

    async def _download_package(
        self,
        plugin_id: str,
        version: str,
        package_url: str,
        *,
        resume: bool = True,
    ) -> Path:
        pkg_name = f"{plugin_id}-{version}.dawnchat"
        out_path = Config.PLUGIN_DOWNLOAD_DIR / pkg_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        task_id = f"plugin_pkg_{self._safe_plugin_dir_name(plugin_id)}_{version}"
        downloader = get_download_router().route(package_url)
        await downloader.start(
            DownloadRequest(
                url=package_url,
                save_path=out_path,
                task_id=task_id,
                use_mirror=None,
                resume=resume,
            )
        )

        async def _on_progress(progress: DownloadProgress):
            if progress.status != "downloading":
                return
            stage_progress = min(34, 10 + int(progress.progress * 0.24))
            self._set_task(
                plugin_id,
                status="downloading_package",
                message="Downloading plugin package",
                progress=stage_progress,
                version=version,
            )

        final_progress = await downloader.wait(
            task_id,
            timeout_s=600,
            poll_interval_s=0.5,
            on_progress=_on_progress,
        )
        if final_progress.status != "completed":
            reason = final_progress.error_message or final_progress.status
            raise RuntimeError(f"Package download failed for {plugin_id}: {reason}")
        return out_path

    @staticmethod
    def _verify_package_sha256(package_path: Path, package_sha256: Optional[str]) -> None:
        if not package_sha256:
            return
        actual = PluginInstallerService._file_sha256(package_path)
        if actual.lower() != package_sha256.lower():
            raise RuntimeError(
                f"Package checksum mismatch (expected={package_sha256}, actual={actual})"
            )

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _safe_plugin_dir_name(plugin_id: str) -> str:
        return plugin_id.replace("/", "_").replace(".", "_")

    async def _run_install(
        self,
        *,
        plugin_id: str,
        version: str,
        package_url: str,
        package_sha256: Optional[str],
    ) -> None:
        try:
            self._set_task(
                plugin_id,
                status="downloading_package",
                message="Downloading plugin package",
                progress=10,
                version=version,
            )
            package_path = await self._download_package(plugin_id, version, package_url, resume=True)
            if package_sha256:
                try:
                    self._verify_package_sha256(package_path, package_sha256)
                except Exception:
                    actual_size = package_path.stat().st_size if package_path.exists() else 0
                    logger.warning(
                        "Package checksum mismatch plugin_id=%s expected_sha=%s actual_size=%s; retrying fresh download",
                        plugin_id,
                        package_sha256,
                        actual_size,
                    )
                    try:
                        package_path.unlink(missing_ok=True)
                    except Exception as cleanup_error:
                        logger.warning(
                            "Failed to remove corrupted package before retry plugin_id=%s path=%s error=%s",
                            plugin_id,
                            package_path,
                            cleanup_error,
                        )
                    self._set_task(
                        plugin_id,
                        status="downloading_package",
                        message="Checksum mismatch, retrying full download",
                        progress=20,
                        version=version,
                    )
                    package_path = await self._download_package(plugin_id, version, package_url, resume=False)
                    try:
                        self._verify_package_sha256(package_path, package_sha256)
                    except Exception:
                        actual = self._file_sha256(package_path)
                        actual_size = package_path.stat().st_size if package_path.exists() else 0
                        raise RuntimeError(
                            f"Package checksum mismatch for {plugin_id} "
                            f"(expected={package_sha256}, actual={actual}, size={actual_size})"
                        )

            self._set_task(
                plugin_id,
                status="extracting",
                message="Extracting package",
                progress=35,
                version=version,
            )
            with TemporaryDirectory(prefix=f"dawnchat-plugin-{plugin_id}-") as tmpdir:
                tmp_root = Path(tmpdir)
                with ZipFile(package_path, "r") as zf:
                    zf.extractall(tmp_root)
                manifests = list(tmp_root.rglob("manifest.json"))
                if not manifests:
                    raise RuntimeError(f"manifest.json missing in package: {plugin_id}")
                manifest_path = manifests[0]
                plugin_root = manifest_path.parent
                target_dir = Config.PLUGIN_SOURCES_DIR / self._safe_plugin_dir_name(plugin_id)
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(plugin_root, target_dir)

            self._set_task(
                plugin_id,
                status="creating_venv",
                message="Creating plugin environment",
                progress=55,
                version=version,
            )
            env_manager = get_env_manager()
            manifest_runtime_isolated = False
            manifest_path = Config.PLUGIN_SOURCES_DIR / self._safe_plugin_dir_name(plugin_id) / "manifest.json"
            if manifest_path.exists():
                try:
                    manifest_model = PluginManifest(**json.loads(manifest_path.read_text(encoding="utf-8")))
                    manifest_runtime_isolated = bool(manifest_model.runtime.isolated)
                except Exception as e:
                    logger.warning("Failed to parse plugin manifest for env policy plugin_id=%s error=%s", plugin_id, e)

            env_decision = await resolve_plugin_env(
                env_manager,
                plugin_id=plugin_id,
                plugin_path=Config.PLUGIN_SOURCES_DIR / self._safe_plugin_dir_name(plugin_id),
                isolated=manifest_runtime_isolated,
                trigger_mode="install",
            )
            venv_path = await env_manager.create_venv(
                plugin_id,
                system_site_packages=env_decision.system_site_packages,
                python_executable=env_decision.python_executable,
                trigger_mode="install",
            )
            if not venv_path:
                raise RuntimeError(f"Failed to create venv for {plugin_id}")

            self._set_task(
                plugin_id,
                status="installing_deps",
                message="Installing plugin dependencies",
                progress=75,
                version=version,
            )
            pyproject_path = (Config.PLUGIN_SOURCES_DIR / self._safe_plugin_dir_name(plugin_id) / "pyproject.toml")
            if pyproject_path.exists():
                ok = await env_manager.install_from_pyproject(plugin_id, pyproject_path)
                if not ok:
                    raise RuntimeError(f"Dependency installation failed for {plugin_id}")

            self._set_task(
                plugin_id,
                status="ready",
                message="Plugin ready",
                progress=100,
                version=version,
            )
        except Exception as e:
            logger.error("Plugin install failed plugin_id=%s error=%s", plugin_id, e, exc_info=True)
            self._set_task(
                plugin_id,
                status="failed",
                message="Plugin install failed",
                progress=100,
                error=str(e),
                version=version,
            )
        finally:
            running = self._running_jobs.get(plugin_id)
            if running and running.done():
                self._running_jobs.pop(plugin_id, None)

    async def cache_template_source(
        self,
        *,
        template_id: str,
        version: str,
        package_url: str,
        package_sha256: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Download and extract a template package to cache directory without creating venv/installing deps.
        """
        safe_name = self._safe_plugin_dir_name(template_id)
        target_root = Config.PLUGIN_TEMPLATE_CACHE_DIR / safe_name / version
        target_source_dir = target_root / "source"
        if target_source_dir.exists() and (target_source_dir / "manifest.json").exists():
            return {
                "template_id": template_id,
                "version": version,
                "cached": True,
                "source_dir": str(target_source_dir),
            }

        target_root.mkdir(parents=True, exist_ok=True)
        package_path = await self._download_package(
            plugin_id=f"template-{template_id}",
            version=version,
            package_url=package_url,
            resume=True,
        )
        self._verify_package_sha256(package_path, package_sha256)

        tmp_dir = target_root / "_tmp_extract"
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        with ZipFile(package_path, "r") as zf:
            zf.extractall(tmp_dir)
        manifests = list(tmp_dir.rglob("manifest.json"))
        if not manifests:
            raise RuntimeError(f"manifest.json missing in template package: {template_id}")
        template_root = manifests[0].parent

        if target_source_dir.exists():
            shutil.rmtree(target_source_dir)
        shutil.copytree(template_root, target_source_dir)
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return {
            "template_id": template_id,
            "version": version,
            "cached": True,
            "source_dir": str(target_source_dir),
        }


_plugin_installer_service: Optional[PluginInstallerService] = None


def get_plugin_installer_service() -> PluginInstallerService:
    global _plugin_installer_service
    if _plugin_installer_service is None:
        _plugin_installer_service = PluginInstallerService()
    return _plugin_installer_service
