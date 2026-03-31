from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from uuid import uuid4
import zipfile

import httpx

from app.config import Config
from app.plugins import get_plugin_manager
from app.utils.logger import get_logger

from .object_storage_client import ObjectStorageClient

logger = get_logger("mobile_publish_service")
DEFAULT_PUBLIC_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtnaWptY3FsYWtrc2poeHNzeGJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3MzQ4MzAsImV4cCI6MjA3ODMxMDgzMH0."
    "-4A6vaGo9RG_jCw6KeiCll_655dpmyU3L11Xhrfuwbk"
)


class MobilePublishError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = str(code or "mobile_publish_failed")
        self.message = str(message or "Mobile publish failed")
        self.status_code = int(status_code)


@dataclass
class MobilePublishTask:
    id: str
    plugin_id: str
    status: str
    stage: str
    progress: int
    message: str
    created_at: str
    updated_at: str
    error: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    requested_version: str = ""


class MobilePublishService:
    def __init__(self) -> None:
        self._storage = ObjectStorageClient()
        self._tasks: dict[str, MobilePublishTask] = {}
        self._task_futures: dict[str, asyncio.Task[None]] = {}

    @staticmethod
    def _create_http_client() -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0),
            follow_redirects=True,
        )

    @staticmethod
    def _log_payload(**payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=True, default=str, sort_keys=True)

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _serialize_task(self, task: MobilePublishTask) -> dict[str, Any]:
        return {
            "id": task.id,
            "plugin_id": task.plugin_id,
            "status": task.status,
            "stage": task.stage,
            "progress": task.progress,
            "message": task.message,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "error": dict(task.error or {}) if task.error else None,
            "result": task.result,
            "requested_version": task.requested_version,
        }

    def _set_task_state(self, task_id: str, **patch: Any) -> MobilePublishTask:
        task = self._tasks[task_id]
        for key, value in patch.items():
            setattr(task, key, value)
        task.updated_at = self._now_iso()
        return task

    def _latest_task_for_plugin(self, plugin_id: str) -> MobilePublishTask | None:
        candidates = [task for task in self._tasks.values() if task.plugin_id == plugin_id]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)

    def _active_task_for_plugin(self, plugin_id: str) -> MobilePublishTask | None:
        for task in self._tasks.values():
            if task.plugin_id == plugin_id and task.status in {"pending", "running"}:
                return task
        return None

    def _functions_base_url(self) -> str:
        supabase_url = Config.SUPABASE_URL
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not configured")
        return f"{supabase_url.rstrip('/')}/functions/v1"

    @staticmethod
    def _resolve_supabase_apikey() -> str:
        for env_name in ("SUPABASE_ANON_KEY", "VITE_SUPABASE_ANON_KEY"):
            value = str(os.getenv(env_name, "")).strip()
            if value:
                return value
        return DEFAULT_PUBLIC_SUPABASE_ANON_KEY

    @staticmethod
    def _parse_semver(version: str) -> tuple[int, int, int]:
        normalized = str(version or "").strip()
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$", normalized)
        if not match:
            raise MobilePublishError("mobile_publish_version_invalid", "版本号必须是合法的 semver，例如 1.2.3")
        return int(match.group(1)), int(match.group(2)), int(match.group(3))

    @classmethod
    def _compare_semver(cls, left: str, right: str) -> int:
        left_value = cls._parse_semver(left)
        right_value = cls._parse_semver(right)
        if left_value < right_value:
            return -1
        if left_value > right_value:
            return 1
        return 0

    @staticmethod
    def _resolve_frontend_root(plugin_path: Path) -> Path:
        frontend_root = plugin_path / "web-src"
        if not frontend_root.exists():
            raise MobilePublishError("mobile_publish_frontend_missing", f"Mobile frontend directory not found: {frontend_root}")
        return frontend_root

    @staticmethod
    def _resolve_build_command(frontend_root: Path) -> tuple[list[str], str]:
        package_json = frontend_root / "package.json"
        if not package_json.exists():
            raise MobilePublishError("mobile_publish_package_json_missing", f"package.json not found: {package_json}")
        bun_binary = Config.get_bun_binary()
        if bun_binary is None or not bun_binary.exists():
            raise MobilePublishError("mobile_publish_bun_missing", "bun binary not found")
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MobilePublishError("mobile_publish_package_json_invalid", f"Failed to parse package.json: {package_json}") from exc
        scripts = payload.get("scripts") or {}
        build_script = str(scripts.get("build") or "").strip()
        if "vite build" in build_script and "--base" not in build_script:
            return (
                [str(bun_binary), "x", "vite", "build", "--base=./"],
                f"{bun_binary} x vite build --base=./",
            )
        return ([str(bun_binary), "run", "build"], f"{bun_binary} run build")

    @classmethod
    async def _run_build(cls, frontend_root: Path) -> str:
        command, display_command = cls._resolve_build_command(frontend_root)
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=str(frontend_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        if process.returncode != 0:
            raise MobilePublishError(
                "mobile_publish_build_failed",
                "Mobile build failed:\n"
                f"{stdout.decode(errors='ignore')}\n"
                f"{stderr.decode(errors='ignore')}",
            )
        return display_command

    @staticmethod
    async def _sha256(path: Path) -> str:
        def _compute() -> str:
            hasher = hashlib.sha256()
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    hasher.update(chunk)
            return hasher.hexdigest()

        return await asyncio.to_thread(_compute)

    @staticmethod
    async def _zip_dist(dist_dir: Path, target_zip: Path) -> int:
        if not dist_dir.exists():
            raise MobilePublishError("mobile_publish_dist_missing", f"Build output directory not found: {dist_dir}")

        def _zip() -> int:
            target_zip.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(target_zip, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for file_path in sorted(item for item in dist_dir.rglob("*") if item.is_file()):
                    arcname = file_path.relative_to(dist_dir).as_posix()
                    archive.write(file_path, arcname=arcname)
            return target_zip.stat().st_size

        return await asyncio.to_thread(_zip)

    async def _invoke_function(
        self,
        *,
        function_name: str,
        token: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        url = f"{self._functions_base_url()}/{function_name}"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "apikey": self._resolve_supabase_apikey(),
        }
        try:
            async with self._create_http_client() as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise MobilePublishError(f"{function_name}_timeout", f"{function_name} timed out") from exc
        except httpx.HTTPError as exc:
            raise MobilePublishError(f"{function_name}_request_failed", f"{function_name} request failed: {exc}") from exc
        if response.status_code >= 400:
            response_text = response.text
            error_code = ""
            error_message = ""
            try:
                response_json = response.json()
                error_code = str(response_json.get("code") or "").strip()
                error_message = str(
                    response_json.get("message")
                    or response_json.get("detail")
                    or response_text
                ).strip()
            except Exception:
                error_message = response_text.strip()
            formatted = f"{function_name} failed"
            if error_code:
                formatted += f" [{error_code}]"
            if error_message:
                formatted += f": {error_message}"
            raise MobilePublishError(error_code or f"{function_name}_failed", formatted)
        return response.json()

    @staticmethod
    def _resolve_target_version(
        requested_version: str | None,
        manifest_version: str,
    ) -> str:
        target_version = str(requested_version or "").strip() or str(manifest_version or "").strip()
        if not target_version:
            raise MobilePublishError("mobile_publish_version_missing", "请先填写发布版本")
        MobilePublishService._parse_semver(target_version)
        return target_version.lstrip("v")

    @staticmethod
    def _read_mobile_versions(plugin_root: Path) -> dict[str, str]:
        manifest_path = plugin_root / "manifest.json"
        package_path = plugin_root / "web-src" / "package.json"
        if not manifest_path.exists():
            raise MobilePublishError("mobile_publish_manifest_missing", f"manifest.json not found: {manifest_path}")
        if not package_path.exists():
            raise MobilePublishError("mobile_publish_package_json_missing", f"package.json not found: {package_path}")
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        package_data = json.loads(package_path.read_text(encoding="utf-8"))
        return {
            "manifest_path": str(manifest_path),
            "package_json_path": str(package_path),
            "manifest_version": str(manifest_data.get("version") or "").strip(),
            "package_version": str(package_data.get("version") or "").strip(),
        }

    @staticmethod
    def _sync_mobile_versions(plugin_root: Path, version: str) -> dict[str, str]:
        manifest_path = plugin_root / "manifest.json"
        package_path = plugin_root / "web-src" / "package.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        package_data = json.loads(package_path.read_text(encoding="utf-8"))
        manifest_data["version"] = version
        package_data["version"] = version
        manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        package_path.write_text(json.dumps(package_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {
            "manifest_version": version,
            "package_version": version,
            "manifest_path": str(manifest_path),
            "package_json_path": str(package_path),
        }

    async def start_publish_task(
        self,
        *,
        plugin_id: str,
        supabase_access_token: str,
        version: str | None = None,
    ) -> dict[str, Any]:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if plugin is None:
            raise MobilePublishError("mobile_publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)
        if str(plugin.manifest.app_type or "desktop") != "mobile":
            raise MobilePublishError("mobile_publish_plugin_not_mobile", "Only mobile plugins can be published")
        active_task = self._active_task_for_plugin(plugin_id)
        if active_task is not None:
            return self._serialize_task(active_task)

        task_id = uuid4().hex
        now = self._now_iso()
        publish_task = MobilePublishTask(
            id=task_id,
            plugin_id=plugin_id,
            status="pending",
            stage="queued",
            progress=0,
            message="等待开始发布",
            created_at=now,
            updated_at=now,
            requested_version=str(version or "").strip(),
        )
        self._tasks[task_id] = publish_task
        self._task_futures[task_id] = asyncio.create_task(
            self._run_publish_task(
                task_id=task_id,
                plugin_id=plugin_id,
                supabase_access_token=supabase_access_token,
                version=version,
            )
        )
        return self._serialize_task(publish_task)

    async def _run_publish_task(
        self,
        *,
        task_id: str,
        plugin_id: str,
        supabase_access_token: str,
        version: str | None,
    ) -> None:
        manager = get_plugin_manager()
        temp_dir = tempfile.mkdtemp(prefix="dawnchat-mobile-publish-")
        try:
            plugin = manager.get_plugin(plugin_id)
            if plugin is None or not plugin.manifest.plugin_path:
                raise MobilePublishError("mobile_publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)
            plugin_root = Path(plugin.manifest.plugin_path)
            frontend_root = self._resolve_frontend_root(plugin_root)
            version_state = self._read_mobile_versions(plugin_root)
            target_version = self._resolve_target_version(version, version_state.get("manifest_version", ""))
            self._set_task_state(task_id, status="running", stage="validating", progress=5, message="正在校验发布信息", requested_version=target_version)

            manifest_version = str(version_state.get("manifest_version") or "")
            package_version = str(version_state.get("package_version") or "")
            remote_version = str((manager.get_plugin_mobile_publish_metadata(plugin_id) or {}).get("last_version") or "")
            if remote_version and self._compare_semver(target_version, remote_version) <= 0:
                raise MobilePublishError("mobile_publish_version_not_greater", f"发布版本必须大于上次发布版本 {remote_version}")

            if manifest_version != target_version or package_version != target_version:
                self._set_task_state(task_id, stage="syncing_version", progress=12, message="正在同步本地源码版本")
                self._sync_mobile_versions(plugin_root, target_version)
                plugin.manifest.version = target_version

            self._set_task_state(task_id, stage="building", progress=28, message="正在构建移动端静态产物")
            build_command = await self._run_build(frontend_root)
            dist_dir = frontend_root / "dist"
            zip_path = Path(temp_dir) / f"{plugin_id}-{target_version}.zip"

            self._set_task_state(task_id, stage="zipping", progress=45, message="正在打包 ZIP 产物")
            zip_size = await self._zip_dist(dist_dir, zip_path)
            zip_sha256 = await self._sha256(zip_path)

            self._set_task_state(task_id, stage="preparing_upload", progress=62, message="正在创建上传凭据")
            prepare = await self._invoke_function(
                function_name="mobile-publish-prepare",
                token=supabase_access_token,
                payload={
                    "plugin_id": plugin_id,
                    "plugin_name": plugin.manifest.name,
                    "version": target_version,
                    "entry": "index.html",
                    "file_name": "bundle.zip",
                    "sha256": zip_sha256,
                    "size": zip_size,
                },
            )

            upload = prepare.get("upload") or {}
            upload_headers = {str(k): str(v) for k, v in dict(upload.get("headers") or {}).items()}
            self._set_task_state(task_id, stage="uploading", progress=78, message="正在上传 ZIP 产物")
            await self._storage.upload_file(
                file_path=zip_path,
                upload_url=str(upload.get("url") or ""),
                headers=upload_headers,
                method=str(upload.get("method") or "PUT"),
            )

            self._set_task_state(task_id, stage="finalizing", progress=92, message="正在生成移动端扫码载荷")
            finalize = await self._invoke_function(
                function_name="mobile-publish-finalize",
                token=supabase_access_token,
                payload={
                    "upload_token": prepare.get("upload_token"),
                    "plugin_id": plugin_id,
                    "plugin_name": plugin.manifest.name,
                    "version": target_version,
                    "entry": "index.html",
                    "bundle_key": prepare.get("bundle_key"),
                },
            )
            payload_json = finalize.get("payload_json") or {}
            result = {
                "plugin_id": plugin_id,
                "version": target_version,
                "bundle_key": str(finalize.get("bundle_key") or prepare.get("bundle_key") or ""),
                "artifact_url": str(finalize.get("artifact_url") or ""),
                "expires_at": str(finalize.get("expires_at") or ""),
                "payload_json": payload_json,
                "payload_text": json.dumps(payload_json, ensure_ascii=False),
                "zip_sha256": zip_sha256,
                "zip_size": zip_size,
                "build_command": build_command,
            }
            manager.update_plugin_mobile_publish_metadata(
                plugin_id,
                {
                    "last_attempt_at": self._now_iso(),
                    "last_version": target_version,
                    "last_status": "completed",
                    "last_result": result,
                    "last_error": "",
                },
            )
            self._set_task_state(
                task_id,
                status="completed",
                stage="completed",
                progress=100,
                message="移动端离线包发布完成",
                error=None,
                result=result,
            )
        except MobilePublishError as error:
            logger.error(
                "Mobile publish task failed %s",
                self._log_payload(plugin_id=plugin_id, task_id=task_id, code=error.code, message=error.message),
            )
            manager.update_plugin_mobile_publish_metadata(
                plugin_id,
                {
                    "last_attempt_at": self._now_iso(),
                    "last_status": "failed",
                    "last_error": error.message,
                },
            )
            self._set_task_state(
                task_id,
                status="failed",
                stage="failed",
                message=error.message,
                error={"code": error.code, "message": error.message},
            )
        except Exception as error:
            logger.exception("Unexpected mobile publish task failure")
            message = str(error or "移动端发布失败")
            manager.update_plugin_mobile_publish_metadata(
                plugin_id,
                {
                    "last_attempt_at": self._now_iso(),
                    "last_status": "failed",
                    "last_error": message,
                },
            )
            self._set_task_state(
                task_id,
                status="failed",
                stage="failed",
                message=message,
                error={"code": "mobile_publish_unexpected_error", "message": message},
            )
        finally:
            self._task_futures.pop(task_id, None)
            shutil.rmtree(temp_dir, ignore_errors=True)

    async def refresh_share_payload(self, plugin_id: str, supabase_access_token: str) -> dict[str, Any]:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if plugin is None:
            raise MobilePublishError("mobile_publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)
        if str(plugin.manifest.app_type or "desktop") != "mobile":
            raise MobilePublishError("mobile_publish_plugin_not_mobile", "Only mobile plugins can be published")
        share = await self._invoke_function(
            function_name="mobile-publish-share",
            token=supabase_access_token,
            payload={"plugin_id": plugin_id},
        )
        payload_json = share.get("payload_json") or {}
        result = {
            "plugin_id": plugin_id,
            "version": str(share.get("version") or ""),
            "bundle_key": str(share.get("bundle_key") or ""),
            "artifact_url": str(share.get("artifact_url") or ""),
            "expires_at": str(share.get("expires_at") or ""),
            "payload_json": payload_json,
            "payload_text": json.dumps(payload_json, ensure_ascii=False),
        }
        manager.update_plugin_mobile_publish_metadata(
            plugin_id,
            {
                "last_status": "completed",
                "last_result": {
                    **dict(manager.get_plugin_mobile_publish_metadata(plugin_id).get("last_result") or {}),
                    **result,
                },
            },
        )
        return result

    async def get_publish_status(self, plugin_id: str) -> dict[str, Any]:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if plugin is None or not plugin.manifest.plugin_path:
            raise MobilePublishError("mobile_publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)
        plugin_root = Path(plugin.manifest.plugin_path)
        version_state = self._read_mobile_versions(plugin_root)
        metadata = manager.get_plugin_mobile_publish_metadata(plugin_id)
        latest_task = self._latest_task_for_plugin(plugin_id)
        return {
            "plugin_id": plugin_id,
            "local_version": version_state.get("manifest_version") or "",
            "manifest_version": version_state.get("manifest_version") or "",
            "package_version": version_state.get("package_version") or "",
            "version_mismatch": bool(
                version_state.get("manifest_version")
                and version_state.get("package_version")
                and version_state.get("manifest_version") != version_state.get("package_version")
            ),
            "last_version": metadata.get("last_version") or None,
            "last_status": metadata.get("last_status") or "draft",
            "last_error": metadata.get("last_error") or None,
            "last_result": metadata.get("last_result") or None,
            "active_task": self._serialize_task(latest_task) if latest_task else None,
            "metadata": metadata,
        }

    def get_publish_task(self, plugin_id: str, task_id: str) -> dict[str, Any]:
        task = self._tasks.get(task_id)
        if task is None or task.plugin_id != plugin_id:
            raise MobilePublishError("mobile_publish_task_not_found", "发布任务不存在", status_code=404)
        return self._serialize_task(task)


_service: MobilePublishService | None = None


def get_mobile_publish_service() -> MobilePublishService:
    global _service
    if _service is None:
        _service = MobilePublishService()
    return _service
