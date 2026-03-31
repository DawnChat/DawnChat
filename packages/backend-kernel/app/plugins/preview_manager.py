"""
Plugin preview runtime manager.

Provides a development preview mode:
- Bun + Vite dev server for frontend hot reload
- File watcher for Python source hot restart
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import socket
import sys
from typing import Optional
import uuid

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.config import Config
from app.utils.logger import get_logger

from .env_manager import UVEnvManager
from .env_policy import resolve_plugin_env
from .models import PluginInfo, PluginPreviewState
from .paths import resolve_plugin_frontend_dir, resolve_plugin_source_root, resolve_runtime_entry
from .plugin_log_service import PluginLogEntry, get_plugin_log_service
from .preview import PreviewSession, PreviewStrategyRegistry

logger = get_logger("plugin_preview_manager")


class _SourceChangeHandler(FileSystemEventHandler):
    def __init__(self, queue: asyncio.Queue[str], loop: asyncio.AbstractEventLoop):
        super().__init__()
        self._queue = queue
        self._loop = loop

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        src_path = str(getattr(event, "src_path", "") or "")
        if not src_path:
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, src_path)


class PluginPreviewManager:
    def __init__(self, env_manager: UVEnvManager):
        self._env_manager = env_manager
        self._sessions: dict[str, PreviewSession] = {}
        self._strategy_registry = PreviewStrategyRegistry()
        self._lock = asyncio.Lock()
        self._allocated_ports: set[int] = set()

    @staticmethod
    def _new_preview_log_session_id() -> str:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        return f"{stamp}-{uuid.uuid4().hex[:8]}"

    async def start_preview(self, plugin: PluginInfo) -> bool:
        if not Config.PLUGIN_PREVIEW_ENABLED:
            plugin.preview.state = PluginPreviewState.ERROR
            plugin.preview.error_message = "Preview mode disabled"
            return False

        async with self._lock:
            existing = self._sessions.get(plugin.manifest.id)
            if existing and not existing.stop_event.is_set():
                plugin.preview.state = PluginPreviewState.RUNNING
                strategy = self._strategy_registry.get(plugin.manifest.app_type)
                plugin.preview.url = strategy.build_url(Config.PLUGIN_PREVIEW_BIND_HOST, existing)
                self._apply_preview_runtime_fields(plugin, existing)
                plugin.preview.error_message = None
                if (
                    str(plugin.manifest.app_type or "").strip().lower() == "desktop"
                    and existing.frontend_mode == "dist"
                    and existing.install_status in {"failed", "idle"}
                ):
                    self.schedule_preview_frontend_install(plugin, existing)
                return True

            strategy = self._strategy_registry.get(plugin.manifest.app_type)
            session = await strategy.create_session(self, plugin)
            if not session.log_session_id:
                session.log_session_id = self._new_preview_log_session_id()
            self._sessions[plugin.manifest.id] = session

            plugin.preview.state = PluginPreviewState.STARTING
            plugin.preview.error_message = None
            plugin.preview.url = None
            self._apply_preview_runtime_fields(plugin, session)

            try:
                await strategy.start(self, plugin, session)
            except Exception as e:
                logger.error("Failed to start preview for %s: %s", plugin.manifest.id, e, exc_info=True)
                await self._stop_preview_locked(plugin, session)
                plugin.preview.state = PluginPreviewState.ERROR
                plugin.preview.error_message = str(e)
                return False

            plugin.preview.state = PluginPreviewState.RUNNING
            plugin.preview.url = strategy.build_url(Config.PLUGIN_PREVIEW_BIND_HOST, session)
            self._apply_preview_runtime_fields(plugin, session)
            plugin.preview.error_message = None
            return True

    async def stop_preview(self, plugin: PluginInfo) -> bool:
        async with self._lock:
            session = self._sessions.get(plugin.manifest.id)
            if not session:
                plugin.preview.state = PluginPreviewState.STOPPED
                plugin.preview.url = None
                plugin.preview.backend_port = None
                plugin.preview.frontend_port = None
                plugin.preview.log_session_id = None
                plugin.preview.error_message = None
                plugin.preview.frontend_mode = "dev"
                plugin.preview.deps_ready = True
                plugin.preview.install_status = "idle"
                plugin.preview.install_error_message = None
                return True
            await self._stop_preview_locked(plugin, session)
            return True

    async def shutdown(self, plugins: dict[str, PluginInfo]) -> None:
        async with self._lock:
            for plugin_id, session in list(self._sessions.items()):
                plugin = plugins.get(plugin_id)
                if plugin is None:
                    continue
                await self._stop_preview_locked(plugin, session)

    async def _stop_preview_locked(self, plugin: PluginInfo, session: PreviewSession) -> None:
        session.stop_event.set()
        if session.watcher_task:
            session.watcher_task.cancel()
            with contextlib.suppress(BaseException):
                await session.watcher_task
            session.watcher_task = None
        if session.install_task:
            session.install_task.cancel()
            with contextlib.suppress(BaseException):
                await session.install_task
            session.install_task = None
        if session.log_tasks:
            for task in session.log_tasks:
                task.cancel()
            for task in session.log_tasks:
                with contextlib.suppress(BaseException):
                    await task
            session.log_tasks = []

        if session.watcher:
            try:
                session.watcher.stop()
                session.watcher.join(timeout=2.0)
            except Exception:
                pass
            session.watcher = None

        await self._terminate_process(session.bun_process, "bun-preview", plugin.manifest.id)
        backend_label = "bun-backend-preview" if session.backend_kind == "bun" else "python-preview"
        await self._terminate_process(session.python_process, backend_label, plugin.manifest.id)
        await self._terminate_process(session.python_sidecar_process, "python-sidecar-preview", plugin.manifest.id)
        session.bun_process = None
        session.python_process = None
        session.python_sidecar_process = None

        if session.backend_port is not None:
            self._release_port(session.backend_port)
        if session.frontend_port is not None:
            self._release_port(session.frontend_port)
        if session.python_sidecar_port is not None:
            self._release_port(session.python_sidecar_port)
        self._sessions.pop(plugin.manifest.id, None)

        plugin.preview.state = PluginPreviewState.STOPPED
        plugin.preview.url = None
        plugin.preview.backend_port = None
        plugin.preview.frontend_port = None
        plugin.preview.log_session_id = None
        plugin.preview.error_message = None
        plugin.preview.frontend_mode = "dev"
        plugin.preview.deps_ready = True
        plugin.preview.install_status = "idle"
        plugin.preview.install_error_message = None
        plugin.preview.python_sidecar_port = None
        plugin.preview.python_sidecar_state = "stopped"
        plugin.preview.python_sidecar_error_message = None

    @staticmethod
    def _apply_preview_runtime_fields(plugin: PluginInfo, session: PreviewSession) -> None:
        plugin.preview.backend_port = session.backend_port
        plugin.preview.frontend_port = session.frontend_port if session.frontend_mode == "dev" else None
        plugin.preview.log_session_id = session.log_session_id
        plugin.preview.frontend_mode = session.frontend_mode
        plugin.preview.deps_ready = session.deps_ready
        plugin.preview.install_status = session.install_status
        plugin.preview.install_error_message = session.install_error_message
        plugin.preview.python_sidecar_port = session.python_sidecar_port
        plugin.preview.python_sidecar_state = session.python_sidecar_state
        plugin.preview.python_sidecar_error_message = session.python_sidecar_error_message

    async def resolve_python_executable(self, plugin: PluginInfo) -> Path:
        plugin_path = resolve_plugin_source_root(plugin.manifest)
        env_decision = await resolve_plugin_env(
            self._env_manager,
            plugin_id=plugin.manifest.id,
            plugin_path=plugin_path,
            isolated=bool(plugin.manifest.runtime.isolated),
            trigger_mode="preview",
        )
        venv_path = await self._env_manager.create_venv(
            plugin.manifest.id,
            system_site_packages=env_decision.system_site_packages,
            python_executable=env_decision.python_executable,
            trigger_mode="preview",
        )
        if venv_path:
            pyproject_path = plugin_path / "pyproject.toml"
            if pyproject_path.exists():
                await self._env_manager.install_from_pyproject(plugin.manifest.id, pyproject_path)
            plugin.venv_path = str(venv_path)
            return self._env_manager.get_venv_python(plugin.manifest.id)
        return Path(sys.executable)

    async def resolve_python_sidecar_executable(
        self,
        plugin: PluginInfo,
        source_root: Path,
        sidecar_entry_path: Path | None,
    ) -> Path:
        if sidecar_entry_path is None:
            return Path(sys.executable)
        env_decision = await resolve_plugin_env(
            self._env_manager,
            plugin_id=plugin.manifest.id,
            plugin_path=source_root,
            isolated=bool(plugin.manifest.runtime.isolated),
            trigger_mode="preview",
        )
        venv_path = await self._env_manager.create_venv(
            plugin.manifest.id,
            system_site_packages=env_decision.system_site_packages,
            python_executable=env_decision.python_executable,
            trigger_mode="preview",
        )
        if venv_path:
            pyproject_path = sidecar_entry_path.parent.parent / "pyproject.toml"
            if pyproject_path.exists():
                await self._env_manager.install_from_pyproject(plugin.manifest.id, pyproject_path)
            plugin.venv_path = str(venv_path)
            return self._env_manager.get_venv_python(plugin.manifest.id)
        return Path(sys.executable)

    @staticmethod
    def resolve_preview_backend(plugin: PluginInfo) -> str:
        app_type = str(plugin.manifest.app_type or "desktop").strip().lower()
        requested = str(plugin.manifest.runtime.backend or "").strip().lower()
        if app_type == "desktop" and requested == "bun":
            return "bun"
        return "python"

    async def start_backend_process(self, plugin: PluginInfo, session: PreviewSession) -> None:
        if session.backend_kind == "bun":
            await self.start_bun_backend_process(plugin, session)
        else:
            await self.start_python_process(plugin, session)
        if session.python_sidecar_entry_path and session.python_sidecar_port:
            try:
                await self.start_python_sidecar_process(plugin, session)
            except Exception as exc:
                session.python_sidecar_state = "error"
                session.python_sidecar_error_message = str(exc)
                logger.warning(
                    "Python sidecar start failed for %s, continue preview without sidecar: %s",
                    plugin.manifest.id,
                    exc,
                )

    async def start_python_process(self, plugin: PluginInfo, session: PreviewSession) -> None:
        if session.entry_path is None:
            raise RuntimeError("Preview Python entry missing")
        if session.python_exe is None:
            raise RuntimeError("Preview Python executable missing")
        if session.backend_port is None:
            raise RuntimeError("Preview backend port missing")
        env = os.environ.copy()
        env["DAWNCHAT_HOST_PORT"] = str(Config.API_PORT)
        env["DAWNCHAT_PLUGIN_ID"] = plugin.manifest.id
        env["DAWNCHAT_PLUGIN_PREVIEW"] = "true"
        env["DAWNCHAT_PLUGIN_LOG_DIR"] = str(get_plugin_log_service().get_main_log_dir())
        env["DAWNCHAT_DATA_DIR"] = str(Config.DATA_DIR)
        env["DAWNCHAT_PLUGIN_SOURCE_DIR"] = str(session.plugin_path)
        env["DAWNCHAT_PLUGIN_DATA_DIR"] = str(Config.PLUGIN_DATA_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["DAWNCHAT_PLUGIN_MODELS_DIR"] = str(Config.PLUGIN_MODELS_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["PYTHONPATH"] = str(session.entry_path.parent)

        cmd = [
            str(session.python_exe),
            str(session.entry_path),
            "--host",
            Config.PLUGIN_PREVIEW_BIND_HOST,
            "--port",
            str(session.backend_port),
        ]
        logger.info("Starting preview Python for %s: %s", plugin.manifest.id, " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(session.entry_path.parent),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.python_process = process
        self._attach_process_log_tasks(plugin.manifest.id, session, process, label="python-preview")
        await asyncio.sleep(1.0)
        if process.returncode is not None and process.returncode != 0:
            raise RuntimeError(
                f"Preview Python failed to start (code={process.returncode}). "
                f"{self._build_log_tail_hint(plugin.manifest.id)}"
            )

    async def start_bun_backend_process(self, plugin: PluginInfo, session: PreviewSession) -> None:
        if session.entry_path is None:
            raise RuntimeError("Preview Bun backend entry missing")
        if session.backend_port is None:
            raise RuntimeError("Preview backend port missing")
        bun_binary = Config.get_bun_binary()
        if bun_binary is None or not bun_binary.exists():
            raise RuntimeError("bun binary not found")

        env = os.environ.copy()
        env["DAWNCHAT_HOST_PORT"] = str(Config.API_PORT)
        env["DAWNCHAT_PLUGIN_ID"] = plugin.manifest.id
        env["DAWNCHAT_PLUGIN_PREVIEW"] = "true"
        env["DAWNCHAT_PLUGIN_BACKEND"] = "bun"
        env["DAWNCHAT_PLUGIN_LOG_DIR"] = str(get_plugin_log_service().get_main_log_dir())
        env["DAWNCHAT_DATA_DIR"] = str(Config.DATA_DIR)
        env["DAWNCHAT_PLUGIN_SOURCE_DIR"] = str(session.plugin_path)
        env["DAWNCHAT_PLUGIN_DATA_DIR"] = str(Config.PLUGIN_DATA_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["DAWNCHAT_PLUGIN_MODELS_DIR"] = str(Config.PLUGIN_MODELS_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["DAWNCHAT_PLUGIN_PORT"] = str(session.backend_port)
        env["DAWNCHAT_PLUGIN_BIND_HOST"] = Config.PLUGIN_PREVIEW_BIND_HOST
        env["PORT"] = str(session.backend_port)
        env["HOST"] = Config.PLUGIN_PREVIEW_BIND_HOST

        cmd = [str(bun_binary), str(session.entry_path)]
        logger.info("Starting preview Bun backend for %s: %s", plugin.manifest.id, " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(session.entry_path.parent),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.python_process = process
        self._attach_process_log_tasks(plugin.manifest.id, session, process, label="bun-backend-preview")
        await asyncio.sleep(1.0)
        if process.returncode is not None and process.returncode != 0:
            raise RuntimeError(
                f"Preview Bun backend failed to start (code={process.returncode}). "
                f"{self._build_log_tail_hint(plugin.manifest.id)}"
            )

    async def start_python_sidecar_process(self, plugin: PluginInfo, session: PreviewSession) -> None:
        if session.python_sidecar_entry_path is None:
            return
        if session.python_sidecar_exe is None:
            raise RuntimeError("Preview Python sidecar executable missing")
        if session.python_sidecar_port is None:
            raise RuntimeError("Preview Python sidecar port missing")
        env = os.environ.copy()
        env["DAWNCHAT_HOST_PORT"] = str(Config.API_PORT)
        env["DAWNCHAT_PLUGIN_ID"] = plugin.manifest.id
        env["DAWNCHAT_PLUGIN_PREVIEW"] = "true"
        env["DAWNCHAT_PLUGIN_LOG_DIR"] = str(get_plugin_log_service().get_main_log_dir())
        env["DAWNCHAT_DATA_DIR"] = str(Config.DATA_DIR)
        env["DAWNCHAT_PLUGIN_SOURCE_DIR"] = str(session.plugin_path)
        env["DAWNCHAT_PLUGIN_DATA_DIR"] = str(Config.PLUGIN_DATA_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["DAWNCHAT_PLUGIN_MODELS_DIR"] = str(Config.PLUGIN_MODELS_DIR / self._safe_plugin_dir_name(plugin.manifest.id))
        env["PYTHONPATH"] = str(session.python_sidecar_entry_path.parent.parent)
        cmd = [
            str(session.python_sidecar_exe),
            str(session.python_sidecar_entry_path),
            "--host",
            Config.PLUGIN_PREVIEW_BIND_HOST,
            "--port",
            str(session.python_sidecar_port),
        ]
        logger.info("Starting preview Python sidecar for %s: %s", plugin.manifest.id, " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(session.python_sidecar_entry_path.parent),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.python_sidecar_process = process
        session.python_sidecar_state = "starting"
        session.python_sidecar_error_message = None
        self._attach_process_log_tasks(plugin.manifest.id, session, process, label="python-sidecar-preview")
        await asyncio.sleep(1.0)
        if process.returncode is not None and process.returncode != 0:
            session.python_sidecar_state = "error"
            session.python_sidecar_error_message = (
                f"Preview Python sidecar failed to start (code={process.returncode})"
            )
            raise RuntimeError(f"{session.python_sidecar_error_message}. {self._build_log_tail_hint(plugin.manifest.id)}")
        session.python_sidecar_state = "running"

    async def start_bun_process(self, plugin: PluginInfo, session: PreviewSession) -> None:
        web_src = resolve_plugin_frontend_dir(plugin.manifest)
        if not web_src.exists():
            # Web source not found, fallback to backend-served UI.
            return

        bun_binary = Config.get_bun_binary()
        if bun_binary is None or not bun_binary.exists():
            raise RuntimeError("bun binary not found")

        logger.info(
            "Preparing web preview dependencies for %s (web_src=%s, frontend_port=%s)",
            plugin.manifest.id,
            web_src,
            session.frontend_port,
        )
        await self._ensure_web_preview_deps(plugin, web_src, bun_binary, session)
        bootstrap = self._ensure_vite_bootstrap_script(web_src)
        frontend_bind_host = self._resolve_frontend_bind_host(plugin)
        cmd = [
            str(bun_binary),
            str(bootstrap),
            str(web_src),
            frontend_bind_host,
            str(session.frontend_port or 0),
            str(session.backend_port or 0),
            plugin.manifest.id,
        ]
        logger.info("Starting preview Bun for %s: %s", plugin.manifest.id, " ".join(cmd))
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(web_src),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        session.bun_process = process
        session.frontend_mode = "dev"
        self._attach_process_log_tasks(plugin.manifest.id, session, process, label="bun-preview")
        await asyncio.sleep(1.0)
        if process.returncode is not None and process.returncode != 0:
            raise RuntimeError(
                f"Preview Bun failed to start (code={process.returncode}). "
                f"{self._build_log_tail_hint(plugin.manifest.id)}"
            )

    def are_preview_frontend_deps_ready(self, plugin: PluginInfo) -> bool:
        web_src = resolve_plugin_frontend_dir(plugin.manifest)
        package_json = web_src / "package.json"
        if not package_json.exists():
            return True
        lock_hash = self._calculate_web_lock_hash(web_src)
        stamp_file = web_src / ".dawnchat-preview" / ".deps-lock.sha256"
        if not stamp_file.exists():
            return False
        previous_hash = stamp_file.read_text(encoding="utf-8").strip()
        node_modules = web_src / "node_modules"
        vite_module = node_modules / "vite"
        return node_modules.exists() and vite_module.exists() and previous_hash == lock_hash

    def schedule_preview_frontend_install(self, plugin: PluginInfo, session: PreviewSession) -> None:
        if session.install_task and not session.install_task.done():
            logger.info("Preview frontend install already running for %s", plugin.manifest.id)
            return
        session.install_status = "running"
        session.install_error_message = None
        self._sync_install_state_to_plugin(plugin, session)
        logger.info(
            "Scheduling preview frontend install for %s (frontend_mode=%s, deps_ready=%s)",
            plugin.manifest.id,
            session.frontend_mode,
            session.deps_ready,
        )
        session.install_task = asyncio.create_task(self._install_preview_frontend_and_switch(plugin, session))

    async def retry_preview_frontend_install(self, plugin: PluginInfo) -> bool:
        async with self._lock:
            session = self._sessions.get(plugin.manifest.id)
            if session is None or session.stop_event.is_set():
                return False
            if session.frontend_mode == "dev" and session.deps_ready:
                return True
            session.install_status = "running"
            session.install_error_message = None
            self._sync_install_state_to_plugin(plugin, session)
            self.schedule_preview_frontend_install(plugin, session)
            return True

    async def _install_preview_frontend_and_switch(self, plugin: PluginInfo, session: PreviewSession) -> None:
        max_attempts = 3
        backoff_seconds = [2.0, 5.0, 12.0]
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "Preview frontend install attempt for %s: %s/%s",
                    plugin.manifest.id,
                    attempt,
                    max_attempts,
                )
                bun_binary = Config.get_bun_binary()
                if bun_binary is None or not bun_binary.exists():
                    raise RuntimeError("bun binary not found")
                web_src = resolve_plugin_frontend_dir(plugin.manifest)
                await self._ensure_web_preview_deps(plugin, web_src, bun_binary, session)
                async with self._lock:
                    current = self._sessions.get(plugin.manifest.id)
                    if current is not session or session.stop_event.is_set():
                        return
                    await self.start_bun_process(plugin, session)
                    session.deps_ready = True
                    session.install_status = "success"
                    session.install_error_message = None
                    strategy = self._strategy_registry.get(plugin.manifest.app_type)
                    plugin.preview.url = strategy.build_url(Config.PLUGIN_PREVIEW_BIND_HOST, session)
                    self._apply_preview_runtime_fields(plugin, session)
                    plugin.preview.state = PluginPreviewState.RUNNING
                    plugin.preview.error_message = None
                logger.info(
                    "Preview frontend install completed for %s (frontend_mode=%s, install_status=%s)",
                    plugin.manifest.id,
                    session.frontend_mode,
                    session.install_status,
                )
                return
            except asyncio.CancelledError:
                raise
            except Exception as e:
                retryable = self._is_retryable_install_error(e)
                user_message = self._format_install_error_message(e)
                if attempt < max_attempts and retryable:
                    delay = backoff_seconds[min(attempt - 1, len(backoff_seconds) - 1)]
                    session.install_status = "running"
                    session.install_error_message = (
                        f"{user_message}，正在重试（{attempt}/{max_attempts - 1}），约 {int(delay)} 秒后继续。"
                    )
                    session.frontend_mode = "dist"
                    session.deps_ready = False
                    async with self._lock:
                        current = self._sessions.get(plugin.manifest.id)
                        if current is not session or session.stop_event.is_set():
                            return
                        self._sync_install_state_to_plugin(plugin, session)
                    logger.warning(
                        "Preview frontend dependency install retry for %s: attempt=%s/%s delay=%.1fs err=%s",
                        plugin.manifest.id,
                        attempt,
                        max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
                    continue

                session.install_status = "failed"
                session.install_error_message = user_message
                session.frontend_mode = "dist"
                session.deps_ready = False
                async with self._lock:
                    current = self._sessions.get(plugin.manifest.id)
                    if current is not session:
                        return
                    self._sync_install_state_to_plugin(plugin, session)
                logger.warning(
                    "Preview frontend dependency install failed for %s after %s attempts: %s",
                    plugin.manifest.id,
                    attempt,
                    e,
                    exc_info=True,
                )
                return

    @staticmethod
    def _is_retryable_install_error(error: Exception) -> bool:
        text = str(error or "").lower()
        if "bun binary not found" in text:
            return False
        markers = [
            "timed out",
            "timeout",
            "network",
            "eai_again",
            "enotfound",
            "ecconnreset",
            "etimedout",
            "connection reset",
            "dns",
            "failed to fetch",
            "getaddrinfo",
        ]
        return any(marker in text for marker in markers)

    @staticmethod
    def _format_install_error_message(error: Exception) -> str:
        text = str(error or "").lower()
        if "bun binary not found" in text:
            return "未找到 Bun 运行环境，无法准备开发模式。"
        if "timed out" in text or "timeout" in text or "code=124" in text:
            return "准备开发环境超时，可能是首次依赖安装较慢。"
        if "eai_again" in text or "enotfound" in text or "dns" in text or "getaddrinfo" in text:
            return "网络不可用，无法下载开发依赖。"
        if "failed to fetch" in text or "network" in text or "connection reset" in text:
            return "网络不稳定，准备开发环境失败。"
        return "准备开发环境失败，请稍后重试。"

    @staticmethod
    def _sync_install_state_to_plugin(plugin: PluginInfo, session: PreviewSession) -> None:
        plugin.preview.install_status = session.install_status
        plugin.preview.install_error_message = session.install_error_message
        plugin.preview.frontend_mode = session.frontend_mode
        plugin.preview.deps_ready = session.deps_ready

    @staticmethod
    def _resolve_frontend_bind_host(plugin: PluginInfo) -> str:
        # Mobile preview needs LAN accessibility for QR-based host app debugging.
        if str(plugin.manifest.app_type or "").strip().lower() == "mobile":
            return "0.0.0.0"
        return Config.PLUGIN_PREVIEW_BIND_HOST

    async def start_watcher(self, plugin: PluginInfo, session: PreviewSession) -> None:
        loop = asyncio.get_running_loop()
        handler = _SourceChangeHandler(session.watcher_queue, loop)
        observer = Observer()
        observer.schedule(handler, str(session.plugin_path), recursive=True)
        observer.start()
        session.watcher = observer
        session.watcher_task = asyncio.create_task(self._watch_loop(plugin, session))

    async def _watch_loop(self, plugin: PluginInfo, session: PreviewSession) -> None:
        debounce_s = max(0.1, Config.PLUGIN_PREVIEW_WATCH_DEBOUNCE_MS / 1000.0)
        while not session.stop_event.is_set():
            changed = await session.watcher_queue.get()
            if session.stop_event.is_set():
                break
            await asyncio.sleep(debounce_s)
            interesting_paths = [changed]
            while True:
                try:
                    interesting_paths.append(session.watcher_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break
            if self._should_restart_backend(plugin, session, interesting_paths):
                await self._restart_backend(plugin, session, interesting_paths)

    async def _restart_backend(self, plugin: PluginInfo, session: PreviewSession, changed_paths: list[str]) -> None:
        plugin.preview.state = PluginPreviewState.RELOADING
        plugin.preview.error_message = None
        backend_label = "Bun backend" if session.backend_kind == "bun" else "Python"
        logger.info(
            "Preview %s reloading for %s, changed=%s",
            backend_label,
            plugin.manifest.id,
            ", ".join(sorted(set(changed_paths))[:10]),
        )

        if session.backend_kind != "bun" and any(path.endswith("pyproject.toml") for path in changed_paths):
            pyproject_path = session.plugin_path / "pyproject.toml"
            if pyproject_path.exists():
                await self._env_manager.install_from_pyproject(plugin.manifest.id, pyproject_path)

        process_label = "bun-backend-preview" if session.backend_kind == "bun" else "python-preview"
        await self._terminate_process(session.python_process, process_label, plugin.manifest.id)
        session.python_process = None
        await self._terminate_process(session.python_sidecar_process, "python-sidecar-preview", plugin.manifest.id)
        session.python_sidecar_process = None
        session.python_sidecar_state = "stopped"
        session.python_sidecar_error_message = None
        await self.start_backend_process(plugin, session)
        self._apply_preview_runtime_fields(plugin, session)
        plugin.preview.state = PluginPreviewState.RUNNING

    @staticmethod
    def _normalize_watch_path(plugin_path: Path, raw_path: str) -> str:
        raw = str(raw_path or "").strip()
        if not raw:
            return ""
        try:
            candidate = Path(raw).resolve()
            base = plugin_path.resolve()
            return candidate.relative_to(base).as_posix()
        except Exception:
            return raw.replace("\\", "/").lstrip("./")

    @staticmethod
    def _derive_backend_scope_posix(plugin: PluginInfo, session: PreviewSession) -> str:
        runtime_root = str(plugin.manifest.runtime.root or "").strip().strip("/")
        entry_path = Path(str(plugin.manifest.runtime.entry or "").strip())
        if entry_path.parts:
            first_segment = entry_path.parts[0]
            backend_scope = Path(runtime_root) / first_segment if runtime_root else Path(first_segment)
            return backend_scope.as_posix().strip("/")
        if session.entry_path is None:
            return ""
        entry_parent = session.entry_path.parent
        try:
            relative = entry_parent.resolve().relative_to(session.plugin_path.resolve())
            return relative.as_posix().strip("/")
        except Exception:
            return ""

    @staticmethod
    def _derive_frontend_scope_posix(plugin: PluginInfo) -> str:
        runtime_root = str(plugin.manifest.runtime.root or "").strip().strip("/")
        frontend_dir = str(plugin.manifest.preview.frontend_dir or "web-src").strip().strip("/")
        if runtime_root:
            return (Path(runtime_root) / frontend_dir).as_posix().strip("/")
        return Path(frontend_dir).as_posix().strip("/")

    @classmethod
    def _should_restart_backend(cls, plugin: PluginInfo, session: PreviewSession, paths: list[str]) -> bool:
        backend_scope = cls._derive_backend_scope_posix(plugin, session)
        frontend_scope = cls._derive_frontend_scope_posix(plugin)
        sidecar_scope = ""
        sidecar_entry_path = getattr(session, "python_sidecar_entry_path", None)
        if sidecar_entry_path is not None:
            try:
                sidecar_scope = sidecar_entry_path.parent.parent.resolve().relative_to(
                    session.plugin_path.resolve()
                ).as_posix().strip("/")
            except Exception:
                sidecar_scope = ""
        for raw in paths:
            path = cls._normalize_watch_path(session.plugin_path, raw)
            if not path:
                continue
            if "/.git/" in path or "/__pycache__/" in path or "/.pytest_cache/" in path:
                continue
            if path.endswith("manifest.json"):
                return True
            if sidecar_scope and (path == sidecar_scope or path.startswith(f"{sidecar_scope}/")):
                if path.endswith(".py") or path.endswith("pyproject.toml"):
                    return True
            if session.backend_kind == "bun":
                if frontend_scope and (path == frontend_scope or path.startswith(f"{frontend_scope}/")):
                    continue
                if path.endswith("package.json") or path.endswith("bun.lock") or path.endswith("bun.lockb"):
                    if backend_scope and not (path == backend_scope or path.startswith(f"{backend_scope}/")):
                        continue
                    return True
                if backend_scope and not (path == backend_scope or path.startswith(f"{backend_scope}/")):
                    continue
                if path.endswith(".ts") or path.endswith(".tsx") or path.endswith(".js") or path.endswith(".mjs"):
                    return True
            else:
                if path.endswith(".py") or path.endswith("pyproject.toml"):
                    return True
        return False

    @staticmethod
    async def _terminate_process(
        process: Optional[asyncio.subprocess.Process],
        label: str,
        plugin_id: str,
    ) -> None:
        if not process:
            return
        if process.returncode is not None:
            return
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.warning("%s did not exit in time, killing: %s", label, plugin_id)
            process.kill()
            await process.wait()
        except Exception as e:
            logger.warning("Failed to terminate %s for %s: %s", label, plugin_id, e)

    def allocate_port(self) -> int:
        port_min, port_max = Config.PLUGIN_PREVIEW_PORT_RANGE
        for port in range(port_min, port_max + 1):
            if port in self._allocated_ports:
                continue
            if not self._is_port_available(port):
                continue
            self._allocated_ports.add(port)
            return port
        raise RuntimeError(f"No available preview ports in range {port_min}-{port_max}")

    def _release_port(self, port: int) -> None:
        self._allocated_ports.discard(port)

    @staticmethod
    def _is_port_available(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((Config.PLUGIN_PREVIEW_BIND_HOST, port))
            except OSError:
                return False
        return True

    @staticmethod
    def _safe_plugin_dir_name(plugin_id: str) -> str:
        return plugin_id.replace("/", "_").replace(".", "_")

    def resolve_preview_entry_path(self, plugin: PluginInfo, plugin_path: Path, backend_kind: str = "python") -> Path:
        del plugin_path  # Kept for backward-compatible signature.
        entry_path = resolve_runtime_entry(plugin.manifest, backend_kind)
        if not entry_path.exists():
            raise RuntimeError(f"Entry not found: {entry_path}")
        return entry_path

    @staticmethod
    def is_python_sidecar_enabled(plugin: PluginInfo) -> bool:
        preview_cfg = getattr(plugin.manifest, "preview", None)
        return bool(getattr(preview_cfg, "python_sidecar_enabled", False))

    @classmethod
    def resolve_python_sidecar_entry_path(cls, plugin: PluginInfo, source_root: Path) -> Path | None:
        if not cls.is_python_sidecar_enabled(plugin):
            return None
        candidate = source_root / "python" / "entry" / "main.py"
        if candidate.exists():
            return candidate
        return None

    def _get_plugin_log_path(self, plugin_id: str) -> Path:
        return get_plugin_log_service().get_main_log_path(plugin_id)

    def _append_backend_log(
        self,
        plugin_id: str,
        *,
        session_id: str,
        message: str,
        level: str = "INFO",
    ) -> None:
        try:
            get_plugin_log_service().append_entries(
                plugin_id,
                [PluginLogEntry(level=level, message=message)],
                mode="preview",
                source="backend",
                session_id=session_id,
            )
        except Exception:
            logger.debug("append preview log failed: plugin=%s", plugin_id, exc_info=True)

    def _attach_process_log_tasks(
        self,
        plugin_id: str,
        session: PreviewSession,
        process: asyncio.subprocess.Process,
        *,
        label: str,
    ) -> None:
        if process.stdout is not None:
            session.log_tasks.append(
                asyncio.create_task(
                    self._pump_process_stream(
                        plugin_id,
                        process.stdout,
                        session_id=session.log_session_id,
                        prefix=f"{label}:stdout",
                    )
                )
            )
        if process.stderr is not None:
            session.log_tasks.append(
                asyncio.create_task(
                    self._pump_process_stream(
                        plugin_id,
                        process.stderr,
                        session_id=session.log_session_id,
                        prefix=f"{label}:stderr",
                    )
                )
            )

    async def _pump_process_stream(
        self,
        plugin_id: str,
        stream: asyncio.StreamReader,
        *,
        session_id: str,
        prefix: str,
    ) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            text = line.decode(errors="replace").strip()
            if not text:
                continue
            self._append_backend_log(
                plugin_id,
                session_id=session_id,
                message=f"[{prefix}] {text}",
            )

    async def _ensure_web_preview_deps(
        self,
        plugin: PluginInfo,
        web_src: Path,
        bun_binary: Path,
        session: PreviewSession,
    ) -> None:
        package_json = web_src / "package.json"
        if not package_json.exists():
            return

        self._validate_vue_sfc_files(web_src)
        lock_hash = self._calculate_web_lock_hash(web_src)
        stamp_dir = web_src / ".dawnchat-preview"
        stamp_dir.mkdir(parents=True, exist_ok=True)
        stamp_file = stamp_dir / ".deps-lock.sha256"
        previous_hash = ""
        if stamp_file.exists():
            previous_hash = stamp_file.read_text(encoding="utf-8").strip()

        node_modules = web_src / "node_modules"
        vite_module = node_modules / "vite"
        needs_install = (not node_modules.exists()) or (not vite_module.exists()) or (lock_hash != previous_hash)
        logger.info(
            "Checking web preview deps for %s (needs_install=%s, node_modules=%s, vite_installed=%s, lock_changed=%s)",
            plugin.manifest.id,
            needs_install,
            node_modules.exists(),
            vite_module.exists(),
            lock_hash != previous_hash,
        )
        if not needs_install:
            logger.info("Web preview deps already ready for %s, skipping install", plugin.manifest.id)
            return

        # IMPORTANT: Preview runtime is owned by sidecar bun.
        # Do not depend on host machine's node/pnpm to avoid environment drift
        # and user-side prerequisite issues.
        cmd = [str(bun_binary), "install"]

        exit_code, stderr_tail = await self._run_command_with_log(
            plugin.manifest.id,
            cmd,
            cwd=web_src,
            timeout_s=240.0,
            session_id=session.log_session_id,
        )
        if exit_code != 0:
            cmd_text = " ".join(cmd)
            hint = stderr_tail or "No stderr output"
            raise RuntimeError(f"Preview web dependencies install failed (code={exit_code}, cmd={cmd_text}). {hint}")

        stamp_file.write_text(lock_hash, encoding="utf-8")
        logger.info("Web preview deps install succeeded for %s", plugin.manifest.id)

    async def _run_command_with_log(
        self,
        plugin_id: str,
        cmd: list[str],
        cwd: Path,
        *,
        timeout_s: Optional[float] = None,
        session_id: str = "",
    ) -> tuple[int, str]:
        self._append_backend_log(
            plugin_id,
            session_id=session_id,
            message=(
                f"[preview-cmd][start] cwd={cwd} "
                f"timeout_s={timeout_s if timeout_s is not None else 'none'} cmd={' '.join(cmd)}"
            ),
        )
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        timed_out = False
        timeout_hint = ""
        try:
            if timeout_s is not None and timeout_s > 0:
                stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=timeout_s)
            else:
                stdout_data, stderr_data = await process.communicate()
        except asyncio.TimeoutError:
            timed_out = True
            timeout_hint = f"Command timed out after {timeout_s:.1f}s"
            logger.warning("%s for %s: %s", timeout_hint, plugin_id, " ".join(cmd))
            terminated = False
            with contextlib.suppress(ProcessLookupError, PermissionError):
                process.terminate()
                terminated = True
            if terminated:
                try:
                    stdout_data, stderr_data = await asyncio.wait_for(process.communicate(), timeout=3.0)
                except asyncio.TimeoutError:
                    killed = False
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        process.kill()
                        killed = True
                    if killed:
                        stdout_data, stderr_data = await process.communicate()
                    else:
                        stdout_data, stderr_data = await process.communicate()
            else:
                stdout_data, stderr_data = await process.communicate()
        stdout_text = stdout_data.decode(errors="replace")
        stderr_text = stderr_data.decode(errors="replace")
        self._append_backend_log(
            plugin_id,
            session_id=session_id,
            message=f"[preview-cmd] {' '.join(cmd)}",
        )
        if stdout_text.strip():
            self._append_backend_log(
                plugin_id,
                session_id=session_id,
                message=f"[preview-cmd][stdout] {stdout_text}",
            )
        if stderr_text.strip():
            self._append_backend_log(
                plugin_id,
                session_id=session_id,
                message=f"[preview-cmd][stderr] {stderr_text}",
            )
        if timed_out:
            self._append_backend_log(
                plugin_id,
                session_id=session_id,
                message=f"[preview-cmd][timeout] {timeout_hint}",
                level="WARN",
            )
        self._append_backend_log(
            plugin_id,
            session_id=session_id,
            message=f"[preview-cmd][exit] code={process.returncode}",
        )
        if timed_out:
            stderr_lines = [stderr_text.strip(), timeout_hint]
            return 124, " | ".join([line for line in stderr_lines if line])
        return process.returncode or 0, self._tail_text(stderr_text, max_lines=8)

    @staticmethod
    def _calculate_web_lock_hash(web_src: Path) -> str:
        hasher = hashlib.sha256()
        for filename in ["package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock", "bun.lock", "bun.lockb"]:
            file_path = web_src / filename
            if file_path.exists():
                hasher.update(file_path.read_bytes())
        return hasher.hexdigest()

    @staticmethod
    def _validate_vue_sfc_files(web_src: Path) -> None:
        src_dir = web_src / "src"
        if not src_dir.exists():
            return
        for vue_file in src_dir.rglob("*.vue"):
            try:
                content = vue_file.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            trimmed = content.strip()
            if not trimmed:
                raise RuntimeError(f"Invalid Vue SFC (empty file): {vue_file}")
            if "<template" not in trimmed and "<script" not in trimmed:
                raise RuntimeError(f"Invalid Vue SFC (missing <template>/<script>): {vue_file}")

    def _build_log_tail_hint(self, plugin_id: str, *, max_lines: int = 12) -> str:
        log_path = self._get_plugin_log_path(plugin_id)
        if not log_path.exists():
            return "No plugin log found"
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception:
            return "Plugin log unreadable"
        if not lines:
            return "Plugin log is empty"
        return "Recent log tail: " + " | ".join(lines[-max_lines:])

    @staticmethod
    def _tail_text(text: str, *, max_lines: int) -> str:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        return " | ".join(lines[-max_lines:])

    @staticmethod
    def _ensure_vite_bootstrap_script(web_src: Path) -> Path:
        script_dir = web_src / ".dawnchat-preview"
        script_dir.mkdir(parents=True, exist_ok=True)
        script_path = script_dir / "vite_preview_server.mjs"
        plugin_dir = Path(__file__).parent
        template_path = plugin_dir / "vite_preview_server_template.mjs"
        if not template_path.exists():
            raise RuntimeError(f"Vite preview template missing: {template_path}")
        script_content = template_path.read_text(encoding="utf-8")
        if not script_path.exists() or script_path.read_text(encoding="utf-8") != script_content:
            script_path.write_text(script_content, encoding="utf-8")
        runtime_src_dir = plugin_dir / "preview_runtime"
        runtime_out_dir = script_dir / "preview_runtime"
        if runtime_src_dir.exists() and runtime_src_dir.is_dir():
            if runtime_out_dir.exists():
                shutil.rmtree(runtime_out_dir)
            shutil.copytree(runtime_src_dir, runtime_out_dir)
        return script_path
