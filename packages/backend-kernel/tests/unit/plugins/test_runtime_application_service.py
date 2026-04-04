import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

import app.plugins.application.runtime_application_service as runtime_module
from app.plugins.application.runtime_application_service import PluginRuntimeApplicationService
from app.plugins.infrastructure.runtime_state_store import PluginRuntimeStateStore
from app.plugins.models import PluginInfo, PluginManifest, PluginRuntimeInfo, PluginState
from app.plugins.registry import PluginRegistry


def _build_plugin(*, app_type: str, backend: str):
    return SimpleNamespace(
        manifest=SimpleNamespace(
            app_type=app_type,
            runtime=SimpleNamespace(backend=backend),
        )
    )


def test_resolve_runtime_backend_uses_bun_only_for_desktop() -> None:
    desktop_plugin = _build_plugin(app_type="desktop", backend="bun")
    web_plugin = _build_plugin(app_type="web", backend="bun")

    assert PluginRuntimeApplicationService.resolve_runtime_backend(desktop_plugin) == "bun"
    assert PluginRuntimeApplicationService.resolve_runtime_backend(web_plugin) == "python"


def test_resolve_runtime_backend_defaults_to_python() -> None:
    plugin = _build_plugin(app_type="desktop", backend="")

    assert PluginRuntimeApplicationService.resolve_runtime_backend(plugin) == "python"


class _EnvManager:
    def __init__(self, *, install_ok: bool = True) -> None:
        self.install_ok = install_ok
        self.install_calls = 0

    async def create_venv(self, *args, **kwargs):
        del args, kwargs
        return Path("/tmp/fake-venv")

    async def install_from_pyproject(self, *args, **kwargs):
        del args, kwargs
        self.install_calls += 1
        return self.install_ok

    def get_venv_python(self, plugin_id: str) -> Path:
        del plugin_id
        return Path(sys.executable)


class _PreviewManager:
    async def stop_preview(self, plugin):
        del plugin
        return None


class _NoopStream:
    async def readline(self):
        return b""


class _StartupProcess:
    def __init__(self) -> None:
        self.pid = 1001
        self.stdout = _NoopStream()
        self.stderr = _NoopStream()

    async def wait(self):
        return 0


class _StopProcess:
    def __init__(self) -> None:
        self.pid = 2001
        self.stdout = _NoopStream()
        self.stderr = _NoopStream()
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def wait(self):
        return 0


def _create_plugin(tmp_path, plugin_id: str = "com.demo.runtime") -> PluginInfo:
    plugin_dir = tmp_path / plugin_id
    (plugin_dir / "src").mkdir(parents=True, exist_ok=True)
    (plugin_dir / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")
    manifest = PluginManifest(
        id=plugin_id,
        name="demo",
        version="1.0.0",
        app_type="desktop",
        min_host_version="0.0.1",
        plugin_path=str(plugin_dir),
    )
    return PluginInfo(manifest=manifest)


def _build_service(registry: PluginRegistry, env_manager: _EnvManager, state_store: PluginRuntimeStateStore):
    return PluginRuntimeApplicationService(
        registry=registry,
        env_manager=env_manager,
        preview_manager=_PreviewManager(),
        runtime_state_store=state_store,
        get_inprocess_manager=lambda: None,
        is_host_compatible=lambda _: True,
    )


@pytest.mark.asyncio
async def test_start_plugin_sets_error_when_startup_timeout(tmp_path, monkeypatch) -> None:
    registry = PluginRegistry()
    plugin = _create_plugin(tmp_path, "com.demo.timeout")
    registry.register(plugin)
    env_manager = _EnvManager()
    state_store = PluginRuntimeStateStore()
    service = _build_service(registry, env_manager, state_store)

    async def _fake_env_decision(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(system_site_packages=False, python_executable=None)

    async def _fake_create_subprocess(*args, **kwargs):
        del args, kwargs
        return _StartupProcess()

    async def _fake_wait_for_ready(*args, **kwargs):
        del args, kwargs
        return False

    monkeypatch.setattr(runtime_module, "resolve_plugin_env", _fake_env_decision)
    monkeypatch.setattr(runtime_module.asyncio, "create_subprocess_exec", _fake_create_subprocess)
    monkeypatch.setattr(service, "wait_for_ready", _fake_wait_for_ready)

    port = await service.start_plugin("com.demo.timeout")

    assert port is None
    assert plugin.state == PluginState.ERROR
    assert plugin.error_message == "Startup timeout"
    assert state_store.get_process("com.demo.timeout") is None


@pytest.mark.asyncio
async def test_start_plugin_sets_error_when_dependency_install_failed(tmp_path, monkeypatch) -> None:
    registry = PluginRegistry()
    plugin = _create_plugin(tmp_path, "com.demo.install-fail")
    Path(plugin.manifest.plugin_path).joinpath("pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    registry.register(plugin)
    env_manager = _EnvManager(install_ok=False)
    state_store = PluginRuntimeStateStore()
    service = _build_service(registry, env_manager, state_store)

    async def _fake_env_decision(*args, **kwargs):
        del args, kwargs
        return SimpleNamespace(system_site_packages=False, python_executable=None)

    monkeypatch.setattr(runtime_module, "resolve_plugin_env", _fake_env_decision)

    port = await service.start_plugin("com.demo.install-fail")

    assert port is None
    assert plugin.state == PluginState.ERROR
    assert plugin.error_message == "Dependency installation failed"
    assert env_manager.install_calls == 1


@pytest.mark.asyncio
async def test_monitor_process_marks_error_on_non_zero_exit(tmp_path) -> None:
    registry = PluginRegistry()
    plugin = _create_plugin(tmp_path, "com.demo.crash")
    plugin.state = PluginState.RUNNING
    plugin.runtime = PluginRuntimeInfo(port=19100)
    registry.register(plugin)
    env_manager = _EnvManager()
    state_store = PluginRuntimeStateStore()
    state_store.set_process("com.demo.crash", _StartupProcess())
    state_store.reserve_port(19100)
    service = _build_service(registry, env_manager, state_store)

    class _CrashProcess(_StartupProcess):
        async def wait(self):
            return 23

    await service.monitor_process("com.demo.crash", _CrashProcess(), session_id="s-monitor")

    assert plugin.state == PluginState.ERROR
    assert plugin.error_message == "Exit code: 23"
    assert state_store.get_process("com.demo.crash") is None
    assert state_store.reserve_port(19100) is True


@pytest.mark.asyncio
async def test_stop_plugin_kills_process_when_graceful_stop_timeout(tmp_path, monkeypatch) -> None:
    registry = PluginRegistry()
    plugin = _create_plugin(tmp_path, "com.demo.stop-timeout")
    plugin.state = PluginState.RUNNING
    plugin.runtime = PluginRuntimeInfo(port=19200)
    registry.register(plugin)
    env_manager = _EnvManager()
    state_store = PluginRuntimeStateStore()
    process = _StopProcess()
    state_store.set_process("com.demo.stop-timeout", process)
    state_store.reserve_port(19200)
    service = _build_service(registry, env_manager, state_store)

    async def _fake_wait_for(coro, timeout):
        del timeout
        await coro
        raise asyncio.TimeoutError

    monkeypatch.setattr(runtime_module.asyncio, "wait_for", _fake_wait_for)

    stopped = await service.stop_plugin("com.demo.stop-timeout")

    assert stopped is True
    assert process.terminated is True
    assert process.killed is True
    assert plugin.state == PluginState.STOPPED
    assert state_store.get_process("com.demo.stop-timeout") is None
    assert state_store.reserve_port(19200) is True
