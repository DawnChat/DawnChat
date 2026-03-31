from __future__ import annotations

import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, Optional
import uuid

from app.config import Config
from app.utils.logger import get_logger

from ..env_manager import UVEnvManager
from ..env_policy import resolve_plugin_env
from ..infrastructure.runtime_state_store import PluginRuntimeStateStore
from ..inprocess_manager import InProcessPluginManager
from ..models import PluginInfo, PluginPreviewState, PluginRuntimeInfo, PluginState
from ..paths import resolve_plugin_frontend_dir, resolve_plugin_source_root, resolve_runtime_entry
from ..plugin_log_service import PluginLogEntry, get_plugin_log_service
from ..preview_manager import PluginPreviewManager
from ..registry import PluginRegistry

logger = get_logger("plugin_runtime_application_service")


class PluginRuntimeApplicationService:
    def __init__(
        self,
        registry: PluginRegistry,
        env_manager: UVEnvManager,
        preview_manager: PluginPreviewManager,
        runtime_state_store: PluginRuntimeStateStore,
        get_inprocess_manager: Callable[[], Optional[InProcessPluginManager]],
        is_host_compatible: Callable[[str], bool],
    ) -> None:
        self._registry = registry
        self._env_manager = env_manager
        self._preview_manager = preview_manager
        self._runtime_state_store = runtime_state_store
        self._get_inprocess_manager = get_inprocess_manager
        self._is_host_compatible = is_host_compatible

    @staticmethod
    def resolve_runtime_backend(plugin: PluginInfo) -> str:
        app_type = str(plugin.manifest.app_type or "desktop").strip().lower()
        requested = str(plugin.manifest.runtime.backend or "").strip().lower()
        if app_type == "desktop" and requested == "bun":
            return "bun"
        return "python"

    def resolve_runtime_entry(self, plugin: PluginInfo, plugin_path: Path, backend: str) -> Path:
        del plugin_path
        return resolve_runtime_entry(plugin.manifest, backend)

    @staticmethod
    def should_try_inprocess(plugin: PluginInfo) -> bool:
        mode = (plugin.manifest.runtime.mode or "").lower()
        return mode == "inprocess"

    async def prepare_plugin_runtime(
        self,
        plugin_id: str,
        *,
        include_python: bool = True,
        include_frontend: bool = True,
    ) -> dict[str, Any]:
        plugin = self._registry.get(plugin_id)
        if plugin is None:
            raise RuntimeError(f"Plugin not found: {plugin_id}")
        if not plugin.manifest.plugin_path:
            raise RuntimeError("Plugin path missing")
        source_root = resolve_plugin_source_root(plugin.manifest)
        app_type = str(plugin.manifest.app_type or "desktop").strip().lower()
        runtime_backend = self.resolve_runtime_backend(plugin)

        prepared_python = False
        prepared_frontend = False

        if include_python and app_type == "desktop" and runtime_backend != "bun":
            env_decision = await resolve_plugin_env(
                self._env_manager,
                plugin_id=plugin_id,
                plugin_path=source_root,
                isolated=bool(plugin.manifest.runtime.isolated),
                trigger_mode="install",
            )
            venv_path = await self._env_manager.create_venv(
                plugin_id,
                system_site_packages=env_decision.system_site_packages,
                python_executable=env_decision.python_executable,
                trigger_mode="install",
            )
            if not venv_path:
                raise RuntimeError(f"Failed to create venv for {plugin_id}")
            plugin.venv_path = str(venv_path)
            pyproject_path = source_root / "pyproject.toml"
            if pyproject_path.exists():
                ok = await self._env_manager.install_from_pyproject(plugin_id, pyproject_path)
                if not ok:
                    raise RuntimeError(f"Dependency installation failed for {plugin_id}")
            prepared_python = True

        if include_frontend and app_type in {"web", "mobile"}:
            web_src = resolve_plugin_frontend_dir(plugin.manifest)
            package_json = web_src / "package.json"
            if package_json.exists():
                bun_binary = Config.get_bun_binary()
                if bun_binary is None or not bun_binary.exists():
                    raise RuntimeError("bun binary not found")
                process = await asyncio.create_subprocess_exec(
                    str(bun_binary),
                    "install",
                    cwd=str(web_src),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr_data = await process.communicate()
                if process.returncode != 0:
                    stderr_text = stderr_data.decode(errors="replace").strip()
                    raise RuntimeError(
                        f"Web runtime dependency install failed for {plugin_id}: {stderr_text or process.returncode}"
                    )
                prepared_frontend = True

        return {
            "plugin_id": plugin_id,
            "app_type": app_type,
            "runtime_backend": runtime_backend,
            "prepared_python": prepared_python,
            "prepared_frontend": prepared_frontend,
        }

    async def start_plugin(self, plugin_id: str) -> Optional[int]:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            logger.error(f"Plugin not found: {plugin_id}")
            return None
        if plugin.state == PluginState.RUNNING:
            logger.warning(f"Plugin already running: {plugin_id}")
            return plugin.runtime.port
        if plugin.state == PluginState.STARTING:
            logger.warning(f"Plugin is already starting: {plugin_id}")
            return None
        if not self._is_host_compatible(plugin.manifest.min_host_version):
            message = f"Host version {Config.VERSION} < required {plugin.manifest.min_host_version}"
            self._registry.update_state(plugin_id, PluginState.ERROR, message)
            logger.error(f"Cannot start plugin {plugin_id}: {message}")
            return None

        try:
            if plugin.preview.state in {
                PluginPreviewState.RUNNING,
                PluginPreviewState.STARTING,
                PluginPreviewState.RELOADING,
            }:
                await self._preview_manager.stop_preview(plugin)
            self._registry.update_state(plugin_id, PluginState.STARTING)
            if not plugin.manifest.plugin_path:
                raise RuntimeError("Plugin path missing")
            source_root = resolve_plugin_source_root(plugin.manifest)
            runtime_backend = self.resolve_runtime_backend(plugin)
            entry_path = self.resolve_runtime_entry(plugin, source_root, runtime_backend)
            if not entry_path.exists():
                raise FileNotFoundError(f"Entry point not found: {entry_path}")

            inprocess_manager = self._get_inprocess_manager()
            if inprocess_manager and self.should_try_inprocess(plugin):
                can_run, reason = inprocess_manager.can_run_inprocess(plugin)
                if can_run:
                    runtime = await inprocess_manager.start_plugin(plugin, entry_path)
                    if runtime:
                        plugin.state = PluginState.RUNNING
                        plugin.runtime = runtime
                        logger.info(f"Plugin started inprocess: {plugin_id}")
                        return runtime.port or Config.API_PORT
                    logger.warning(f"Inprocess start failed for {plugin_id}, fallback to process mode")
                else:
                    logger.info(f"Inprocess not supported for {plugin_id}: {reason}")

            venv_path: Optional[Path] = None
            if runtime_backend == "python":
                env_decision = await resolve_plugin_env(
                    self._env_manager,
                    plugin_id=plugin_id,
                    plugin_path=source_root,
                    isolated=bool(plugin.manifest.runtime.isolated),
                    trigger_mode="runtime",
                )
                venv_path = await self._env_manager.create_venv(
                    plugin_id,
                    system_site_packages=env_decision.system_site_packages,
                    python_executable=env_decision.python_executable,
                    trigger_mode="runtime",
                )
                if venv_path:
                    plugin.venv_path = str(venv_path)
                    pyproject_path = source_root / "pyproject.toml"
                    if pyproject_path.exists():
                        ok = await self._env_manager.install_from_pyproject(plugin_id, pyproject_path)
                        if not ok:
                            self._registry.update_state(plugin_id, PluginState.ERROR, "Dependency installation failed")
                            return None

            port = self._allocate_port()
            runtime_session_id = self._new_runtime_log_session_id()
            self._runtime_state_store.set_runtime_log_session(plugin_id, runtime_session_id)

            env = os.environ.copy()
            env["DAWNCHAT_HOST_PORT"] = str(Config.API_PORT)
            env["DAWNCHAT_PLUGIN_ID"] = plugin_id
            env["DAWNCHAT_PLUGIN_BACKEND"] = runtime_backend
            env["DAWNCHAT_PLUGIN_LOG_DIR"] = str(self._get_plugin_log_dir())
            env["DAWNCHAT_DATA_DIR"] = str(Config.DATA_DIR)
            env["DAWNCHAT_PLUGIN_SOURCE_DIR"] = str(source_root)
            env["DAWNCHAT_PLUGIN_DATA_DIR"] = str(self._get_plugin_data_dir(plugin_id))
            env["DAWNCHAT_PLUGIN_MODELS_DIR"] = str(self._get_plugin_models_dir(plugin_id))

            from app.services.ffmpeg_manager import inject_ffmpeg_env

            inject_ffmpeg_env(env)
            if plugin_id == "com.dawnchat.comfyui":
                env = self._strip_ffmpeg_libs(env)

            if runtime_backend == "python":
                if venv_path:
                    python_exe = self._env_manager.get_venv_python(plugin_id)
                else:
                    python_exe = Path(sys.executable)
                env["PYTHONPATH"] = str(entry_path.parent)
                nltk_data_dir = Config.NLTK_DATA_DIR
                if not nltk_data_dir.exists():
                    try:
                        nltk_data_dir.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        logger.warning(f"Failed to create NLTK data dir: {e}")
                env["NLTK_DATA"] = str(nltk_data_dir)
                cmd = [
                    str(python_exe),
                    str(entry_path),
                    "--port",
                    str(port),
                    "--host",
                    "127.0.0.1",
                ]
            else:
                bun_binary = Config.get_bun_binary()
                if bun_binary is None or not bun_binary.exists():
                    raise RuntimeError("bun binary not found")
                env["DAWNCHAT_PLUGIN_PORT"] = str(port)
                env["DAWNCHAT_PLUGIN_BIND_HOST"] = "127.0.0.1"
                env["PORT"] = str(port)
                env["HOST"] = "127.0.0.1"
                cmd = [str(bun_binary), str(entry_path)]

            logger.info("Starting plugin %s (backend=%s): %s", plugin_id, runtime_backend, " ".join(cmd))
            process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(entry_path.parent),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._runtime_state_store.set_process(plugin_id, process)
            ready = await self.wait_for_ready(
                plugin_id,
                process,
                timeout=30.0,
                session_id=runtime_session_id,
            )
            if ready:
                plugin.state = PluginState.RUNNING
                plugin.runtime = PluginRuntimeInfo(
                    process_id=process.pid,
                    port=port,
                    started_at=datetime.now(),
                    health_check_url=f"http://127.0.0.1:{port}/",
                    gradio_url=f"http://127.0.0.1:{port}/",
                )
                asyncio.create_task(self.monitor_process(plugin_id, process, session_id=runtime_session_id))
                logger.info(f"Plugin started: {plugin_id} on port {port}")
                return port
            await self.cleanup_process(plugin_id, process, port)
            self._registry.update_state(plugin_id, PluginState.ERROR, "Startup timeout")
            return None
        except Exception as e:
            logger.error(f"Failed to start plugin {plugin_id}: {e}", exc_info=True)
            self._registry.update_state(plugin_id, PluginState.ERROR, str(e))
            return None

    async def wait_for_ready(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        timeout: float = 30.0,
        *,
        session_id: str,
    ) -> bool:
        try:
            async def read_stderr():
                if process.stderr is None:
                    return False
                while True:
                    line = await process.stderr.readline()
                    if not line:
                        break
                    text = line.decode(errors="replace").strip()
                    if not text:
                        continue
                    self._append_runtime_log(plugin_id, session_id=session_id, message=f"[stderr] {text}")
                    try:
                        data = json.loads(text)
                        if data.get("status") == "ready":
                            logger.info(f"Plugin {plugin_id} ready: {data}")
                            return True
                    except json.JSONDecodeError:
                        logger.debug(f"[{plugin_id}] {text}")
                    except Exception as e:
                        logger.warning(f"Error parsing plugin output: {e}")
                return False

            result = await asyncio.wait_for(read_stderr(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.error(f"Plugin {plugin_id} startup timeout")
            return False
        except Exception as e:
            logger.error(f"Error waiting for plugin ready: {e}")
            return False

    async def monitor_process(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        *,
        session_id: str,
    ) -> None:
        try:
            async def read_output(stream, prefix):
                if stream is None:
                    return
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    text = line.decode(errors="replace").strip()
                    if text:
                        logger.debug(f"[{plugin_id}] {prefix}: {text}")
                        self._append_runtime_log(plugin_id, session_id=session_id, message=f"[{prefix}] {text}")

            await asyncio.gather(
                read_output(process.stdout, "stdout"),
                read_output(process.stderr, "stderr"),
            )
            return_code = await process.wait()
            logger.info(f"Plugin {plugin_id} exited with code {return_code}")
            plugin = self._registry.get(plugin_id)
            if plugin and plugin.state == PluginState.RUNNING:
                if return_code == 0:
                    self._registry.update_state(plugin_id, PluginState.STOPPED)
                else:
                    self._registry.update_state(plugin_id, PluginState.ERROR, f"Exit code: {return_code}")
            if plugin and plugin.runtime.port:
                self._release_port(plugin.runtime.port)
            self._runtime_state_store.pop_process(plugin_id)
        except Exception as e:
            logger.error(f"Error monitoring plugin {plugin_id}: {e}")
        finally:
            self._runtime_state_store.pop_runtime_log_session(plugin_id)

    async def stop_plugin(self, plugin_id: str) -> bool:
        plugin = self._registry.get(plugin_id)
        if not plugin:
            logger.error(f"Plugin not found: {plugin_id}")
            return False
        if plugin.state != PluginState.RUNNING:
            logger.warning(f"Plugin not running: {plugin_id} (state: {plugin.state.value})")
            return True

        inprocess_manager = self._get_inprocess_manager()
        if inprocess_manager and inprocess_manager.is_running(plugin_id):
            try:
                self._registry.update_state(plugin_id, PluginState.STOPPING)
                stopped = await inprocess_manager.stop_plugin(plugin_id)
                if stopped:
                    self._registry.update_state(plugin_id, PluginState.STOPPED)
                    logger.info(f"Plugin stopped inprocess: {plugin_id}")
                    return True
                self._registry.update_state(plugin_id, PluginState.ERROR, "Inprocess stop failed")
                return False
            except Exception as e:
                logger.error(f"Failed to stop inprocess plugin {plugin_id}: {e}", exc_info=True)
                self._registry.update_state(plugin_id, PluginState.ERROR, str(e))
                return False

        process = self._runtime_state_store.get_process(plugin_id)
        if not process:
            logger.warning(f"No process found for plugin: {plugin_id}")
            self._registry.update_state(plugin_id, PluginState.STOPPED)
            return True

        try:
            self._registry.update_state(plugin_id, PluginState.STOPPING)
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(f"Plugin {plugin_id} did not exit gracefully, killing")
                process.kill()
                await process.wait()
            await self.cleanup_process(plugin_id, process, plugin.runtime.port)
            self._registry.update_state(plugin_id, PluginState.STOPPED)
            logger.info(f"Plugin stopped: {plugin_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to stop plugin {plugin_id}: {e}", exc_info=True)
            return False

    async def cleanup_process(
        self,
        plugin_id: str,
        process: asyncio.subprocess.Process,
        port: Optional[int],
    ) -> None:
        if port:
            self._release_port(port)
        self._runtime_state_store.pop_process(plugin_id)
        self._runtime_state_store.pop_runtime_log_session(plugin_id)

    async def restart_plugin(self, plugin_id: str) -> Optional[int]:
        await self.stop_plugin(plugin_id)
        return await self.start_plugin(plugin_id)

    def _allocate_port(self) -> int:
        port_min, port_max = Config.PLUGIN_PORT_RANGE
        for port in range(port_min, port_max + 1):
            if self._runtime_state_store.reserve_port(port):
                return port
        raise RuntimeError(f"No available ports in range {port_min}-{port_max}")

    def _release_port(self, port: int) -> None:
        self._runtime_state_store.release_port(port)

    def _get_plugin_log_dir(self) -> Path:
        return get_plugin_log_service().get_main_log_dir()

    @staticmethod
    def _safe_plugin_dir_name(plugin_id: str) -> str:
        return plugin_id.replace("/", "_").replace(".", "_")

    def _get_plugin_data_dir(self, plugin_id: str) -> Path:
        path = Config.PLUGIN_DATA_DIR / self._safe_plugin_dir_name(plugin_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_plugin_models_dir(self, plugin_id: str) -> Path:
        path = Config.PLUGIN_MODELS_DIR / self._safe_plugin_dir_name(plugin_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _new_runtime_log_session_id() -> str:
        stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
        return f"{stamp}-{uuid.uuid4().hex[:8]}"

    def _append_runtime_log(self, plugin_id: str, *, session_id: str, message: str, level: str = "INFO") -> None:
        try:
            get_plugin_log_service().append_entries(
                plugin_id,
                [PluginLogEntry(level=level, message=message)],
                mode="runtime",
                source="backend",
                session_id=session_id,
            )
        except Exception:
            logger.debug("append runtime log failed: plugin=%s", plugin_id, exc_info=True)

    def _strip_ffmpeg_libs(self, env: dict[str, str]) -> dict[str, str]:
        ffmpeg_lib = str(Config.FFMPEG_DIR / "lib")
        for key in ("DYLD_LIBRARY_PATH", "DYLD_FALLBACK_LIBRARY_PATH", "LD_LIBRARY_PATH"):
            if key not in env:
                continue
            parts = [p for p in env[key].split(os.pathsep) if p and p != ffmpeg_lib]
            if parts:
                env[key] = os.pathsep.join(parts)
            else:
                env.pop(key, None)
        return env
