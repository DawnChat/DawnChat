from dataclasses import dataclass
from datetime import datetime
import importlib
from importlib import util as importlib_util
import os
from pathlib import Path
import re
import sys
from typing import Any, Optional, cast

from fastapi import FastAPI
from starlette.routing import Mount

from app.config import Config
from app.utils.logger import get_logger

from .models import PluginInfo, PluginRuntimeInfo

logger = get_logger("plugin_inprocess_manager")


@dataclass
class InProcessHandle:
    mount: Mount
    app: FastAPI
    lifespan: Optional[Any]
    sys_path_entry: Optional[str]
    sdk_path_added: bool
    runtime: PluginRuntimeInfo


class InProcessPluginManager:
    def __init__(self, app: FastAPI):
        self._app = app
        self._handles: dict[str, InProcessHandle] = {}
        self._host_dependencies = self._load_host_dependencies()
        self._sdk_path = Config.PROJECT_ROOT / "sdk"
        self._sdk_path_refcount = 0

    def is_running(self, plugin_id: str) -> bool:
        return plugin_id in self._handles

    def can_run_inprocess(self, plugin: PluginInfo) -> tuple[bool, str]:
        runtime = getattr(plugin.manifest, "runtime", None)
        ui = getattr(plugin.manifest, "ui", None)
        if runtime is None or ui is None:
            return False, "missing_runtime_or_ui"
        runtime_mode = (runtime.mode or "").lower()
        if runtime_mode != "inprocess":
            return False, "runtime_mode_not_inprocess"
        ui_type = (ui.type or "").lower()
        if ui_type != "web":
            return False, "ui_not_web"
        framework = (ui.framework or "").lower()
        if framework != "vue":
            return False, "ui_not_vue"
        if plugin.manifest.capabilities.gradio.enabled or plugin.manifest.capabilities.nicegui.enabled:
            return False, "ui_incompatible"
        if not plugin.manifest.plugin_path:
            return False, "missing_plugin_path"
        plugin_path = Path(plugin.manifest.plugin_path)
        deps = self._get_plugin_dependencies(plugin_path / "pyproject.toml")
        unsupported = [dep for dep in deps if not self._is_dependency_allowed(dep)]
        if unsupported:
            return False, f"unsupported_dependencies:{','.join(unsupported)}"
        return True, ""

    async def start_plugin(self, plugin: PluginInfo, entry_path: Path) -> Optional[PluginRuntimeInfo]:
        plugin_id = plugin.manifest.id
        if plugin_id in self._handles:
            return self._handles[plugin_id].runtime
        if not plugin.manifest.plugin_path:
            return None
        plugin_path = Path(plugin.manifest.plugin_path)
        if not entry_path.exists():
            logger.error(f"Inprocess entry not found for {plugin_id}: {entry_path}")
            return None
        sys_path_entry = self._ensure_sys_path(plugin_path / "src")
        sdk_path_added = self._ensure_sdk_path()
        prev_env = self._set_env(plugin_id)
        try:
            module = self._load_module(entry_path, plugin_id)
            create_app = getattr(module, "create_app", None)
            if not callable(create_app):
                logger.error(f"Inprocess entry missing create_app() for {plugin_id}: {entry_path}")
                self._release_sdk_path(sdk_path_added)
                self._remove_sys_path(sys_path_entry)
                return None
            sub_app = create_app(plugin_path)
        except Exception as exc:
            logger.error(f"Inprocess entry load failed for {plugin_id}: {exc}", exc_info=True)
            self._release_sdk_path(sdk_path_added)
            self._remove_sys_path(sys_path_entry)
            return None
        finally:
            self._restore_env(prev_env)
        if not isinstance(sub_app, FastAPI):
            logger.error(f"Inprocess create_app() did not return FastAPI for {plugin_id}")
            self._release_sdk_path(sdk_path_added)
            self._remove_sys_path(sys_path_entry)
            return None
        sub_app = cast(FastAPI, sub_app)
        lifespan_context = sub_app.router.lifespan_context(sub_app)
        if lifespan_context is None:
            logger.error(f"Inprocess lifespan unavailable for {plugin_id}")
            self._release_sdk_path(sdk_path_added)
            self._remove_sys_path(sys_path_entry)
            return None
        lifespan_context = cast(Any, lifespan_context)
        try:
            await lifespan_context.__aenter__()
        except Exception as exc:
            logger.error(f"Inprocess lifespan failed for {plugin_id}: {exc}", exc_info=True)
            try:
                await lifespan_context.__aexit__(None, None, None)
            except Exception:
                pass
            self._release_sdk_path(sdk_path_added)
            self._remove_sys_path(sys_path_entry)
            return None
        base_path = f"/plugins/{plugin_id}"
        mount = Mount(base_path, app=cast(Any, sub_app), name=f"plugin-{plugin_id}")
        self._app.router.routes.append(mount)
        ui = getattr(plugin.manifest, "ui", None)
        entry = ui.entry if ui and ui.entry is not None else "/"
        url_path = self._join_paths(base_path, entry)
        runtime = PluginRuntimeInfo(
            process_id=None,
            port=Config.API_PORT,
            started_at=datetime.now(),
            health_check_url=f"http://{Config.API_HOST}:{Config.API_PORT}{url_path}",
            gradio_url=f"http://{Config.API_HOST}:{Config.API_PORT}{url_path}",
        )
        self._handles[plugin_id] = InProcessHandle(
            mount=mount,
            app=sub_app,
            lifespan=lifespan_context,
            sys_path_entry=sys_path_entry,
            sdk_path_added=sdk_path_added,
            runtime=runtime,
        )
        return runtime

    async def stop_plugin(self, plugin_id: str) -> bool:
        handle = self._handles.pop(plugin_id, None)
        if not handle:
            return False
        self._app.router.routes = [route for route in self._app.router.routes if route is not handle.mount]
        if handle.lifespan is not None:
            try:
                lifespan = cast(Any, handle.lifespan)
                await lifespan.__aexit__(None, None, None)
            except Exception as exc:
                logger.warning(f"Inprocess shutdown error for {plugin_id}: {exc}")
        self._release_sdk_path(handle.sdk_path_added)
        self._remove_sys_path(handle.sys_path_entry)
        return True

    def _load_module(self, entry_path: Path, plugin_id: str):
        module_name = f"dawnchat_plugin_{plugin_id.replace('.', '_')}"
        spec = importlib_util.spec_from_file_location(module_name, entry_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Failed to load spec for {entry_path}")
        module = importlib_util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module

    def _set_env(self, plugin_id: str) -> dict[str, Optional[str]]:
        prev = {
            "DAWNCHAT_PLUGIN_ID": os.environ.get("DAWNCHAT_PLUGIN_ID"),
            "DAWNCHAT_HOST_PORT": os.environ.get("DAWNCHAT_HOST_PORT"),
            "DAWNCHAT_PLUGIN_BASE_PATH": os.environ.get("DAWNCHAT_PLUGIN_BASE_PATH"),
            "DAWNCHAT_INPROCESS": os.environ.get("DAWNCHAT_INPROCESS"),
        }
        os.environ["DAWNCHAT_PLUGIN_ID"] = plugin_id
        os.environ["DAWNCHAT_HOST_PORT"] = str(Config.API_PORT)
        os.environ["DAWNCHAT_PLUGIN_BASE_PATH"] = f"/plugins/{plugin_id}"
        os.environ["DAWNCHAT_INPROCESS"] = "1"
        return prev

    def _restore_env(self, prev: dict[str, Optional[str]]) -> None:
        for key, value in prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _ensure_sys_path(self, path: Path) -> Optional[str]:
        path_str = str(path)
        if path_str in sys.path:
            return None
        sys.path.insert(0, path_str)
        return path_str

    def _remove_sys_path(self, path_str: Optional[str]) -> None:
        if not path_str:
            return
        if path_str in sys.path:
            sys.path.remove(path_str)

    def _ensure_sdk_path(self) -> bool:
        if not self._sdk_path.exists():
            return False
        sdk_str = str(self._sdk_path)
        if sdk_str in sys.path:
            return False
        sys.path.insert(0, sdk_str)
        self._sdk_path_refcount += 1
        return True

    def _release_sdk_path(self, added: bool) -> None:
        if not added:
            return
        self._sdk_path_refcount = max(0, self._sdk_path_refcount - 1)
        if self._sdk_path_refcount == 0:
            sdk_str = str(self._sdk_path)
            if sdk_str in sys.path:
                sys.path.remove(sdk_str)

    def _join_paths(self, base: str, entry: str) -> str:
        base_clean = base.rstrip("/")
        entry_clean = (entry or "").strip()
        if not entry_clean or entry_clean == "/":
            return f"{base_clean}/"
        return f"{base_clean}/{entry_clean.lstrip('/')}"

    def _load_host_dependencies(self) -> set[str]:
        pyproject_path = Config.BACKEND_ROOT / "pyproject.toml"
        deps = self._get_dependencies_from_pyproject(pyproject_path)
        return {self._normalize_name(dep) for dep in deps}

    def _get_plugin_dependencies(self, pyproject_path: Path) -> list[str]:
        return self._get_dependencies_from_pyproject(pyproject_path)

    def _get_dependencies_from_pyproject(self, pyproject_path: Path) -> list[str]:
        if not pyproject_path.exists():
            return []
        data = None
        try:
            try:
                toml_loader = importlib.import_module("tomllib")
            except ModuleNotFoundError:
                toml_loader = importlib.import_module("tomli")
            with open(pyproject_path, "rb") as f:
                data = toml_loader.load(f)
        except Exception:
            return []
        deps = data.get("project", {}).get("dependencies", []) or []
        if not isinstance(deps, list):
            return []
        names: list[str] = []
        for dep in deps:
            if not isinstance(dep, str):
                continue
            name = self._extract_name(dep)
            if name:
                names.append(name)
        return names

    def _extract_name(self, requirement: str) -> str:
        pattern = r"^[A-Za-z0-9_.-]+"
        match = re.match(pattern, requirement.strip())
        return match.group(0) if match else ""

    def _normalize_name(self, name: str) -> str:
        return name.strip().lower().replace("_", "-")

    def _is_dependency_allowed(self, name: str) -> bool:
        normalized = self._normalize_name(name)
        if normalized in self._host_dependencies:
            return True
        if normalized == "dawnchat-sdk" or normalized.startswith("dawnchat-sdk["):
            return self._sdk_path.exists()
        return False
