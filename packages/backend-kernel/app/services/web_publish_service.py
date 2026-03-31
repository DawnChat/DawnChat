from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

import httpx

from app.config import Config
from app.plugins import get_plugin_manager
from app.utils.logger import get_logger

from .object_storage_client import ObjectStorageClient

logger = get_logger("web_publish_service")
DEFAULT_PUBLIC_SUPABASE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtnaWptY3FsYWtrc2poeHNzeGJiIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjI3MzQ4MzAsImV4cCI6MjA3ODMxMDgzMH0."
    "-4A6vaGo9RG_jCw6KeiCll_655dpmyU3L11Xhrfuwbk"
)


class WebPublishError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = str(code or "web_publish_failed")
        self.message = str(message or "Web publish failed")
        self.status_code = int(status_code)


@dataclass
class BuildArtifact:
    path: str
    absolute_path: Path
    size: int
    sha256: str
    content_type: str


@dataclass
class WebPublishTask:
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
    requested_slug: str = ""
    requested_version: str = ""


class WebPublishService:
    def __init__(self) -> None:
        self._storage = ObjectStorageClient()
        self._tasks: dict[str, WebPublishTask] = {}
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

    @staticmethod
    def _runtime_origin() -> str:
        return str(os.getenv("SITE_RUNTIME_ORIGIN", "https://sites.dawnchat.com") or "https://sites.dawnchat.com").rstrip("/")

    @classmethod
    def _private_runtime_url(cls, slug: str) -> str:
        normalized = str(slug or "").strip()
        return f"{cls._runtime_origin()}/my-sites/{normalized}" if normalized else ""

    @classmethod
    def _public_runtime_url(cls, public_slug: str) -> str:
        normalized = str(public_slug or "").strip()
        return f"{cls._runtime_origin()}/sites/{normalized}" if normalized else ""

    @staticmethod
    def _parse_semver(version: str) -> tuple[int, int, int]:
        normalized = str(version or "").strip()
        match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?$", normalized)
        if not match:
            raise WebPublishError("publish_version_invalid", "版本号必须是合法的 semver，例如 1.2.3")
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

    def _serialize_task(self, task: WebPublishTask) -> dict[str, Any]:
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
            "requested_slug": task.requested_slug,
            "requested_version": task.requested_version,
        }

    def _set_task_state(self, task_id: str, **patch: Any) -> WebPublishTask:
        task = self._tasks[task_id]
        for key, value in patch.items():
            setattr(task, key, value)
        task.updated_at = self._now_iso()
        return task

    def _latest_task_for_plugin(self, plugin_id: str) -> WebPublishTask | None:
        candidates = [task for task in self._tasks.values() if task.plugin_id == plugin_id]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)

    def _active_task_for_plugin(self, plugin_id: str) -> WebPublishTask | None:
        for task in self._tasks.values():
            if task.plugin_id == plugin_id and task.status in {"pending", "running"}:
                return task
        return None

    @staticmethod
    def _extract_html_asset_refs(html: str, attribute: str) -> list[str]:
        pattern = re.compile(rf"{attribute}=[\"']([^\"']+)[\"']", re.IGNORECASE)
        refs: list[str] = []
        seen: set[str] = set()
        for match in pattern.finditer(html):
            value = str(match.group(1) or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            refs.append(value)
        return refs

    @classmethod
    def _summarize_index_html(cls, index_html_path: Path) -> dict[str, Any]:
        try:
            html = index_html_path.read_text(encoding="utf-8")
        except Exception as exc:
            return {
                "path": str(index_html_path),
                "read_error": str(exc),
            }

        normalized = " ".join(html.split())
        return {
            "path": str(index_html_path),
            "size": len(html.encode("utf-8")),
            "has_base_tag": "<base" in html.lower(),
            "has_nonce_attr": " nonce=" in html.lower(),
            "script_srcs": cls._extract_html_asset_refs(html, "src"),
            "style_hrefs": cls._extract_html_asset_refs(html, "href"),
            "preview": normalized[:280],
        }

    async def close(self) -> None:
        await self._storage.close()

    def _functions_base_url(self) -> str:
        supabase_url = Config.SUPABASE_URL
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not configured")
        return f"{supabase_url.rstrip('/')}/functions/v1"

    def _rest_base_url(self) -> str:
        supabase_url = Config.SUPABASE_URL
        if not supabase_url:
            raise RuntimeError("SUPABASE_URL is not configured")
        return f"{supabase_url.rstrip('/')}/rest/v1"

    @staticmethod
    def _resolve_supabase_apikey() -> str:
        for env_name in ("SUPABASE_ANON_KEY", "VITE_SUPABASE_ANON_KEY"):
            value = str(os.getenv(env_name, "")).strip()
            if value:
                return value
        return DEFAULT_PUBLIC_SUPABASE_ANON_KEY

    @classmethod
    def _rest_headers(cls, token: str) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "apikey": cls._resolve_supabase_apikey(),
        }
        return headers

    @staticmethod
    def _resolve_frontend_root(plugin_path: Path) -> Path:
        frontend_root = plugin_path / "web-src"
        if not frontend_root.exists():
            raise WebPublishError("publish_frontend_missing", f"Web frontend directory not found: {frontend_root}")
        return frontend_root

    @staticmethod
    def _resolve_build_command(frontend_root: Path) -> tuple[list[str], str]:
        package_json = frontend_root / "package.json"
        if not package_json.exists():
            raise WebPublishError("publish_package_json_missing", f"package.json not found: {package_json}")
        bun_binary = Config.get_bun_binary()
        if bun_binary is None or not bun_binary.exists():
            raise WebPublishError("publish_bun_missing", "bun binary not found")
        try:
            payload = json.loads(package_json.read_text(encoding="utf-8"))
        except Exception as exc:
            raise WebPublishError("publish_package_json_invalid", f"Failed to parse package.json: {package_json}") from exc
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
            raise WebPublishError(
                "publish_build_failed",
                "Web build failed:\n"
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

    async def _collect_build_artifacts(self, dist_dir: Path) -> list[BuildArtifact]:
        if not dist_dir.exists():
            raise WebPublishError("publish_dist_missing", f"Build output directory not found: {dist_dir}")
        artifacts: list[BuildArtifact] = []
        for file_path in sorted(item for item in dist_dir.rglob("*") if item.is_file()):
            relative = file_path.relative_to(dist_dir).as_posix()
            content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
            artifacts.append(
                BuildArtifact(
                    path=relative,
                    absolute_path=file_path,
                    size=file_path.stat().st_size,
                    sha256=await self._sha256(file_path),
                    content_type=content_type,
                )
            )
        if not any(item.path == "index.html" for item in artifacts):
            raise WebPublishError("publish_index_missing", "Build output missing index.html")
        return artifacts

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
        logger.info(
            "Invoking web publish edge function %s",
            self._log_payload(
                function_name=function_name,
                url=url,
                payload_keys=sorted(payload.keys()),
                has_apikey=bool(headers.get("apikey")),
            ),
        )
        try:
            async with self._create_http_client() as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            logger.error(
                "Web publish edge function timed out %s",
                self._log_payload(
                    function_name=function_name,
                    url=url,
                    error=str(exc),
                ),
            )
            raise WebPublishError(f"{function_name}_timeout", f"{function_name} timed out") from exc
        except httpx.HTTPError as exc:
            logger.error(
                "Web publish edge function request failed %s",
                self._log_payload(
                    function_name=function_name,
                    url=url,
                    error=str(exc),
                ),
            )
            raise WebPublishError(f"{function_name}_request_failed", f"{function_name} request failed: {exc}") from exc
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
            logger.error(
                "Web publish edge function failed %s",
                self._log_payload(
                    function_name=function_name,
                    status_code=response.status_code,
                    response_text=response_text,
                ),
            )
            raise WebPublishError(error_code or f"{function_name}_failed", formatted)
        return response.json()

    async def _fetch_release_by_id(self, headers: dict[str, str], release_id: str) -> dict[str, Any] | None:
        async with self._create_http_client() as client:
            response = await client.get(
                f"{self._rest_base_url()}/web_app_releases",
                headers=headers,
                params={
                    "select": "id,version,status,published_at,storage_prefix,entry_file,router_mode",
                    "id": f"eq.{release_id}",
                    "limit": "1",
                },
            )
        if response.status_code >= 400:
            raise WebPublishError(
                "publish_status_remote_failed",
                f"查询线上版本失败: {response.text.strip() or response.status_code}",
            )
        releases = response.json() or []
        return releases[0] if releases else None

    async def _fetch_latest_published_release(self, headers: dict[str, str], web_app_id: str) -> dict[str, Any] | None:
        async with self._create_http_client() as client:
            response = await client.get(
                f"{self._rest_base_url()}/web_app_releases",
                headers=headers,
                params={
                    "select": "id,version,status,published_at,storage_prefix,entry_file,router_mode",
                    "web_app_id": f"eq.{web_app_id}",
                    "status": "eq.published",
                    "order": "published_at.desc,created_at.desc",
                    "limit": "1",
                },
            )
        if response.status_code >= 400:
            raise WebPublishError(
                "publish_status_remote_failed",
                f"查询线上最新版本失败: {response.text.strip() or response.status_code}",
            )
        releases = response.json() or []
        return releases[0] if releases else None

    async def _fetch_remote_publish_snapshot(self, token: str, plugin_id: str) -> dict[str, Any]:
        headers = self._rest_headers(token)
        web_app_params = {
            "select": "id,slug,public_slug,visibility,status,current_release_id,updated_at",
            "plugin_id": f"eq.{plugin_id}",
            "order": "updated_at.desc",
            "limit": "1",
        }
        logger.info(
            "Querying remote publish snapshot %s",
            self._log_payload(
                plugin_id=plugin_id,
                rest_url=f"{self._rest_base_url()}/web_apps",
                has_access_token=bool(str(token or "").strip()),
                has_apikey=bool(headers.get("apikey")),
                web_app_params=web_app_params,
            ),
        )
        try:
            async with self._create_http_client() as client:
                web_app_response = await client.get(
                    f"{self._rest_base_url()}/web_apps",
                    headers=headers,
                    params=web_app_params,
                )
        except httpx.HTTPError as exc:
            raise WebPublishError("publish_status_remote_failed", f"查询线上发布状态失败: {exc}") from exc
        if web_app_response.status_code >= 400:
            logger.error(
                "Remote publish snapshot query failed %s",
                self._log_payload(
                    plugin_id=plugin_id,
                    status_code=web_app_response.status_code,
                    response_text=web_app_response.text.strip(),
                    has_apikey=bool(headers.get("apikey")),
                ),
            )
            raise WebPublishError(
                "publish_status_remote_failed",
                f"查询线上发布状态失败: {web_app_response.text.strip() or web_app_response.status_code}",
            )
        web_apps = web_app_response.json() or []
        web_app = web_apps[0] if web_apps else None
        if not web_app:
            logger.info(
                "Remote publish snapshot returned no web app %s",
                self._log_payload(plugin_id=plugin_id),
            )
            return {
                "web_app_id": None,
                "slug": "",
                "status": "draft",
                "current_release_id": None,
                "remote_latest_version": None,
                "remote_release_status": None,
                "last_published_at": None,
                "visibility": "private",
                "public_slug": None,
                "private_runtime_url": "",
                "public_runtime_url": "",
                "runtime_url": "",
            }

        current_release_id = str(web_app.get("current_release_id") or "").strip() or None
        release_payload: dict[str, Any] | None = None
        if current_release_id:
            try:
                release_payload = await self._fetch_release_by_id(headers, current_release_id)
            except httpx.HTTPError as exc:
                raise WebPublishError("publish_status_remote_failed", f"查询线上版本失败: {exc}") from exc
            logger.info(
                "Resolved current remote release %s",
                self._log_payload(
                    plugin_id=plugin_id,
                    web_app_id=str(web_app.get("id") or ""),
                    current_release_id=current_release_id,
                    release_found=bool(release_payload),
                    release_status=(release_payload or {}).get("status"),
                    release_version=(release_payload or {}).get("version"),
                ),
            )

        if not release_payload:
            web_app_id = str(web_app.get("id") or "").strip()
            if web_app_id:
                try:
                    release_payload = await self._fetch_latest_published_release(headers, web_app_id)
                except httpx.HTTPError as exc:
                    raise WebPublishError("publish_status_remote_failed", f"查询线上最新版本失败: {exc}") from exc
                logger.info(
                    "Resolved fallback remote release %s",
                    self._log_payload(
                        plugin_id=plugin_id,
                        web_app_id=web_app_id,
                        current_release_id=current_release_id,
                        fallback_release_id=(release_payload or {}).get("id"),
                        fallback_release_status=(release_payload or {}).get("status"),
                        fallback_release_version=(release_payload or {}).get("version"),
                    ),
                )

        slug = str(web_app.get("slug") or "").strip()
        public_slug = str(web_app.get("public_slug") or "").strip() or None
        visibility = str(web_app.get("visibility") or "private").strip() or "private"
        private_runtime_url = self._private_runtime_url(slug)
        public_runtime_url = self._public_runtime_url(public_slug or "")
        runtime_url = private_runtime_url if visibility == "private" else (public_runtime_url or private_runtime_url)
        snapshot = {
            "web_app_id": str(web_app.get("id") or "").strip() or None,
            "slug": slug,
            "public_slug": public_slug,
            "visibility": visibility,
            "status": str(web_app.get("status") or "draft"),
            "current_release_id": current_release_id,
            "remote_latest_version": str((release_payload or {}).get("version") or "").strip() or None,
            "remote_release_status": str((release_payload or {}).get("status") or "").strip() or None,
            "last_published_at": (release_payload or {}).get("published_at"),
            "private_runtime_url": private_runtime_url,
            "public_runtime_url": public_runtime_url,
            "runtime_url": runtime_url,
        }
        logger.info(
            "Remote publish snapshot resolved %s",
            self._log_payload(
                plugin_id=plugin_id,
                web_app_id=snapshot["web_app_id"],
                slug=snapshot["slug"],
                public_slug=snapshot["public_slug"],
                visibility=snapshot["visibility"],
                status=snapshot["status"],
                current_release_id=snapshot["current_release_id"],
                remote_latest_version=snapshot["remote_latest_version"],
                remote_release_status=snapshot["remote_release_status"],
                last_published_at=snapshot["last_published_at"],
            ),
        )
        return snapshot

    @staticmethod
    def _resolve_publish_slug(plugin_id: str, requested_slug: str | None) -> str:
        value = str(requested_slug or "").strip()
        return value or plugin_id.split(".")[-1]

    def _resolve_target_version(
        self,
        *,
        local_state: dict[str, Any],
        remote_state: dict[str, Any],
        requested_version: str | None,
    ) -> str:
        target_version = str(requested_version or local_state.get("resolved_version") or "").strip()
        if not target_version:
            raise WebPublishError("publish_version_missing", "请先填写发布版本")
        self._parse_semver(target_version)
        remote_latest_version = str(remote_state.get("remote_latest_version") or "").strip()
        if remote_latest_version and self._compare_semver(target_version, remote_latest_version) <= 0:
            raise WebPublishError(
                "publish_version_not_greater",
                f"发布版本必须大于线上最新版本 {remote_latest_version}",
            )
        return target_version

    async def start_publish_task(
        self,
        *,
        plugin_id: str,
        supabase_access_token: str,
        slug: str | None = None,
        title: str | None = None,
        description: str | None = None,
        version: str | None = None,
        initial_visibility: str | None = None,
    ) -> dict[str, Any]:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if plugin is None:
            raise WebPublishError("publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)
        if str(plugin.manifest.app_type or "desktop") != "web":
            raise WebPublishError("publish_plugin_not_web", "Only web plugins can be published")
        active_task = self._active_task_for_plugin(plugin_id)
        if active_task is not None:
            return self._serialize_task(active_task)

        task_id = uuid4().hex
        now = self._now_iso()
        publish_task = WebPublishTask(
            id=task_id,
            plugin_id=plugin_id,
            status="pending",
            stage="queued",
            progress=0,
            message="等待开始发布",
            created_at=now,
            updated_at=now,
            requested_slug=self._resolve_publish_slug(plugin_id, slug),
            requested_version=str(version or "").strip(),
        )
        self._tasks[task_id] = publish_task
        self._task_futures[task_id] = asyncio.create_task(
            self._run_publish_task(
                task_id=task_id,
                plugin_id=plugin_id,
                supabase_access_token=supabase_access_token,
                slug=slug,
                title=title,
                description=description,
                version=version,
                initial_visibility=initial_visibility,
            )
        )
        return self._serialize_task(publish_task)

    async def _run_publish_task(
        self,
        *,
        task_id: str,
        plugin_id: str,
        supabase_access_token: str,
        slug: str | None,
        title: str | None,
        description: str | None,
        version: str | None,
        initial_visibility: str | None,
    ) -> None:
        manager = get_plugin_manager()
        try:
            self._set_task_state(task_id, status="running", stage="validating", progress=5, message="正在校验版本与线上状态")
            local_versions = manager.get_web_plugin_versions(plugin_id)
            remote_state = await self._fetch_remote_publish_snapshot(supabase_access_token, plugin_id)
            target_version = self._resolve_target_version(
                local_state=local_versions,
                remote_state=remote_state,
                requested_version=version,
            )

            self._set_task_state(task_id, requested_version=target_version)
            if (
                str(local_versions.get("manifest_version") or "") != target_version
                or str(local_versions.get("package_version") or "") != target_version
            ):
                self._set_task_state(task_id, stage="syncing_version", progress=12, message="正在同步本地源码版本")
                local_versions = manager.sync_web_plugin_versions(plugin_id, target_version)

            plugin = manager.get_plugin(plugin_id)
            if plugin is None or not plugin.manifest.plugin_path:
                raise WebPublishError("publish_plugin_not_found", f"Plugin not found: {plugin_id}", status_code=404)

            plugin_path = Path(plugin.manifest.plugin_path)
            frontend_root = self._resolve_frontend_root(plugin_path)
            publish_slug = self._resolve_publish_slug(plugin_id, slug)
            publish_title = title or plugin.manifest.name
            publish_description = description if description is not None else plugin.manifest.description

            logger.info(
                "Starting web plugin publish task %s",
                self._log_payload(
                    plugin_id=plugin.manifest.id,
                    task_id=task_id,
                    plugin_name=plugin.manifest.name,
                    frontend_root=str(frontend_root),
                    slug=publish_slug,
                    version=target_version,
                    remote_latest_version=remote_state.get("remote_latest_version"),
                ),
            )

            self._set_task_state(task_id, stage="building", progress=25, message="正在构建网页产物")
            build_command = await self._run_build(frontend_root)
            dist_dir = frontend_root / "dist"
            artifacts = await self._collect_build_artifacts(dist_dir)
            index_html_summary = self._summarize_index_html(dist_dir / "index.html")
            logger.info(
                "Web build artifacts collected %s",
                self._log_payload(
                    plugin_id=plugin.manifest.id,
                    task_id=task_id,
                    dist_dir=str(dist_dir),
                    artifact_count=len(artifacts),
                    build_command=build_command,
                    artifact_paths_sample=[item.path for item in artifacts[:10]],
                    index_html=index_html_summary,
                ),
            )

            payload = {
                "plugin_id": plugin.manifest.id,
                "slug": publish_slug,
                "title": publish_title,
                "description": publish_description,
                "framework": plugin.manifest.ui.framework or "vue",
                "version": target_version,
                "initial_visibility": (
                    str(initial_visibility or "").strip()
                    if str(initial_visibility or "").strip() in {"private", "public", "unlisted"}
                    else "private"
                ),
                "entry_file": "index.html",
                "router_mode": "history",
                "manifest_json": {
                    "files": [
                        {
                            "path": item.path,
                            "sha256": item.sha256,
                            "size": item.size,
                            "content_type": item.content_type,
                        }
                        for item in artifacts
                    ],
                    "output_dir": "web-src/dist",
                    "build_command": build_command,
                },
                "build_meta": {
                    "plugin_id": plugin.manifest.id,
                    "plugin_name": plugin.manifest.name,
                    "built_at": self._now_iso(),
                    "artifact_count": len(artifacts),
                },
            }

            self._set_task_state(task_id, stage="preparing_upload", progress=55, message="正在创建线上发布记录")
            prepare = await self._invoke_function(
                function_name="web-publish-prepare",
                token=supabase_access_token,
                payload=payload,
            )
            logger.info(
                "Web publish prepare completed %s",
                self._log_payload(
                    plugin_id=plugin.manifest.id,
                    task_id=task_id,
                    release_id=str(prepare["release"]["id"]),
                    upload_count=len(prepare.get("uploads") or []),
                    runtime_url=prepare.get("runtime_url"),
                    storage_bucket=str(prepare["release"].get("storage_bucket") or ""),
                    storage_prefix=str(prepare["release"].get("storage_prefix") or ""),
                ),
            )

            uploads = []
            upload_map = {item.path: item for item in artifacts}
            for item in prepare.get("uploads") or []:
                artifact = upload_map.get(str(item.get("path") or ""))
                if artifact is None:
                    raise WebPublishError(
                        "publish_prepare_mismatch",
                        f"Unexpected upload target returned by prepare: {item.get('path')}",
                    )
                uploads.append({
                    "file_path": artifact.absolute_path,
                    "upload": item.get("upload") or {},
                    "path": artifact.path,
                })

            self._set_task_state(task_id, stage="uploading", progress=65, message="正在上传网页资源")

            async def _on_uploaded(index: int, total: int, item: dict[str, Any]) -> None:
                progress = 65 if total <= 0 else min(90, 65 + int(index / total * 25))
                self._set_task_state(
                    task_id,
                    stage="uploading",
                    progress=progress,
                    message=f"正在上传网页资源（{index}/{total}）",
                )

            await self._storage.upload_many(uploads, on_uploaded=_on_uploaded)
            logger.info(
                "Web publish asset upload completed %s",
                self._log_payload(
                    plugin_id=plugin.manifest.id,
                    task_id=task_id,
                    release_id=str(prepare["release"]["id"]),
                    upload_count=len(uploads),
                ),
            )

            self._set_task_state(task_id, stage="finalizing", progress=95, message="正在完成发布")
            finalize = await self._invoke_function(
                function_name="web-publish-finalize",
                token=supabase_access_token,
                payload={"release_id": prepare["release"]["id"]},
            )
            logger.info(
                "Web publish finalized %s",
                self._log_payload(
                    plugin_id=plugin.manifest.id,
                    task_id=task_id,
                    release_id=str(finalize["release"]["id"]),
                    status=str(finalize["release"]["status"]),
                ),
            )

            result = {
                "plugin_id": plugin_id,
                "web_app": prepare["web_app"],
                "release": {
                    **dict(finalize["release"]),
                    "version": prepare["release"]["version"],
                },
                "runtime_url": (
                    str(finalize.get("public_runtime_url") or "").strip()
                    if str(prepare["web_app"].get("visibility") or "private") != "private"
                    else str(finalize.get("private_runtime_url") or prepare.get("private_runtime_url") or prepare.get("runtime_url") or "")
                ),
                "private_runtime_url": str(finalize.get("private_runtime_url") or prepare.get("private_runtime_url") or ""),
                "public_runtime_url": str(finalize.get("public_runtime_url") or prepare.get("public_runtime_url") or ""),
                "artifact_count": len(artifacts),
                "local_version": target_version,
                "remote_latest_version": prepare["release"]["version"],
            }
            publish_meta = {
                "last_attempt_at": self._now_iso(),
                "last_release_id": str(finalize["release"]["id"]),
                "last_runtime_url": str(result.get("runtime_url") or ""),
                "last_private_runtime_url": str(result.get("private_runtime_url") or ""),
                "last_public_runtime_url": str(result.get("public_runtime_url") or ""),
                "last_slug": str(prepare["web_app"]["slug"]),
                "last_public_slug": str(prepare["web_app"].get("public_slug") or ""),
                "last_visibility": str(prepare["web_app"].get("visibility") or "private"),
                "last_version": str(prepare["release"]["version"]),
                "last_status": str(finalize["release"]["status"]),
                "local_version": target_version,
                "remote_latest_version": str(prepare["release"]["version"]),
                "last_published_at": str(finalize["release"].get("published_at") or ""),
            }
            manager.update_plugin_publish_metadata(plugin_id, publish_meta)
            self._set_task_state(
                task_id,
                status="completed",
                stage="completed",
                progress=100,
                message="发布完成",
                error=None,
                result=result,
            )
        except WebPublishError as error:
            logger.error(
                "Web publish task failed %s",
                self._log_payload(plugin_id=plugin_id, task_id=task_id, code=error.code, message=error.message),
            )
            manager.update_plugin_publish_metadata(
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
            logger.exception("Unexpected web publish task failure")
            message = str(error or "发布失败")
            manager.update_plugin_publish_metadata(
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
                error={"code": "publish_unexpected_error", "message": message},
            )
        finally:
            self._task_futures.pop(task_id, None)

    async def get_publish_status(self, plugin_id: str, supabase_access_token: str | None = None) -> dict[str, Any]:
        manager = get_plugin_manager()
        local_state = manager.get_web_plugin_versions(plugin_id)
        metadata = manager.get_plugin_publish_metadata(plugin_id)
        remote_state: dict[str, Any] = {}
        remote_error: dict[str, Any] | None = None
        if supabase_access_token:
            try:
                remote_state = await self._fetch_remote_publish_snapshot(supabase_access_token, plugin_id)
            except WebPublishError as error:
                remote_error = {"code": error.code, "message": error.message}

        latest_task = self._latest_task_for_plugin(plugin_id)
        return {
            "plugin_id": plugin_id,
            "local_version": local_state.get("resolved_version") or "",
            "manifest_version": local_state.get("manifest_version") or "",
            "package_version": local_state.get("package_version") or "",
            "version_mismatch": bool(local_state.get("version_mismatch")),
            "remote_latest_version": remote_state.get("remote_latest_version") or metadata.get("remote_latest_version") or metadata.get("last_version") or None,
            "remote_release_status": remote_state.get("remote_release_status") or metadata.get("last_status") or None,
            "current_status": remote_state.get("status") or metadata.get("last_status") or "draft",
            "current_slug": remote_state.get("slug") or metadata.get("last_slug") or "",
            "visibility": remote_state.get("visibility") or metadata.get("last_visibility") or "private",
            "public_slug": remote_state.get("public_slug") or metadata.get("last_public_slug") or None,
            "private_runtime_url": remote_state.get("private_runtime_url") or metadata.get("last_private_runtime_url") or self._private_runtime_url(remote_state.get("slug") or metadata.get("last_slug") or ""),
            "public_runtime_url": remote_state.get("public_runtime_url") or metadata.get("last_public_runtime_url") or self._public_runtime_url(remote_state.get("public_slug") or metadata.get("last_public_slug") or ""),
            "runtime_url": remote_state.get("runtime_url") or metadata.get("last_runtime_url") or "",
            "last_published_at": remote_state.get("last_published_at") or metadata.get("last_published_at") or None,
            "active_task": self._serialize_task(latest_task) if latest_task else None,
            "metadata": metadata,
            "remote_error": remote_error,
        }

    def get_publish_task(self, plugin_id: str, task_id: str) -> dict[str, Any]:
        task = self._tasks.get(task_id)
        if task is None or task.plugin_id != plugin_id:
            raise WebPublishError("publish_task_not_found", "发布任务不存在", status_code=404)
        return self._serialize_task(task)


_service: WebPublishService | None = None


def get_web_publish_service() -> WebPublishService:
    global _service
    if _service is None:
        _service = WebPublishService()
    return _service
