import pytest

from app.config import Config
from app.services import opencode_manager as opencode_manager_module
from app.services.opencode_manager import OpenCodeManager, OpenCodeReadyResult, OpenCodeStatus


class _ProcessStub:
    def __init__(self, pid: int = 1234, returncode=None):
        self.pid = pid
        self.returncode = returncode
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True
        self.returncode = 0

    def kill(self):
        self.killed = True
        self.returncode = -9

    async def wait(self):
        return self.returncode


class _RulesServiceStub:
    def get_current_dir(self) -> str:
        return ""


@pytest.mark.asyncio
async def test_health_payload_contains_last_start_failure_snapshot(monkeypatch: pytest.MonkeyPatch):
    manager = OpenCodeManager()
    manager._status = OpenCodeStatus.ERROR
    manager._workspace_path = None
    manager._last_start_failure = {
        "reason": "startup_exception",
        "error_type": "RuntimeError",
        "error_message": "boom",
        "hint": "failed to start",
    }
    async def _always_unhealthy() -> bool:
        return False

    monkeypatch.setattr(manager, "health_check", _always_unhealthy)

    payload = await manager.get_health_payload()

    assert payload["status"] == "error"
    assert payload["healthy"] is False
    assert payload["last_start_failure"]["reason"] == "startup_exception"
    assert payload["last_start_failure"]["error_message"] == "boom"


@pytest.mark.asyncio
async def test_start_does_not_short_circuit_when_status_starting_but_unhealthy(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    manager = OpenCodeManager()
    workspace = tmp_path
    manager._status = OpenCodeStatus.STARTING
    manager._workspace_path = workspace

    async def _always_unhealthy() -> bool:
        return False

    monkeypatch.setattr(manager, "health_check", _always_unhealthy)
    monkeypatch.setattr(Config, "get_opencode_binary", staticmethod(lambda: None))

    ok = await manager.start(str(workspace))

    assert ok is False
    assert manager.status == OpenCodeStatus.ERROR


@pytest.mark.asyncio
async def test_start_allocates_dynamic_port_and_uses_it_everywhere(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    manager = OpenCodeManager()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    binary = tmp_path / "opencode"
    binary.write_text("", encoding="utf-8")
    process = _ProcessStub(pid=2468)
    captured: dict[str, object] = {}

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return process

    async def _fake_build_baseline_config():
        captured["baseline_port"] = manager.port
        return {"server": {"port": manager.port}}

    async def _fake_wait_until_ready(timeout: float) -> OpenCodeReadyResult:
        captured["wait_timeout"] = timeout
        return OpenCodeReadyResult(ready=True, listener_pid=process.pid)

    monkeypatch.setattr(Config, "get_opencode_binary", staticmethod(lambda: binary))
    monkeypatch.setattr(opencode_manager_module, "get_opencode_rules_service", lambda: _RulesServiceStub())
    monkeypatch.setattr(opencode_manager_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(manager, "_clear_quarantine_if_needed", lambda _binary: None)
    monkeypatch.setattr(manager, "_ensure_health_loop", lambda: None)
    monkeypatch.setattr(manager, "_allocate_runtime_port", lambda: 55123)
    monkeypatch.setattr(manager, "_build_baseline_config", _fake_build_baseline_config)
    monkeypatch.setattr(manager, "_wait_until_ready", _fake_wait_until_ready)

    ok = await manager.start(
        str(workspace),
        startup_context={"workspace_kind": "plugin-dev", "plugin_id": "com.demo.current"},
    )

    assert ok is True
    assert manager.port == 55123
    assert manager.base_url == "http://127.0.0.1:55123"
    assert captured["baseline_port"] == 55123
    assert "--port" in captured["cmd"]
    assert "55123" in captured["cmd"]
    assert captured["cwd"] == str(workspace)
    assert captured["env"]["OPENCODE_CONFIG_CONTENT"] == '{"server": {"port": 55123}}'


@pytest.mark.asyncio
async def test_wait_until_ready_fails_when_listener_pid_mismatches(monkeypatch: pytest.MonkeyPatch):
    manager = OpenCodeManager()
    manager._runtime_port = 55123
    manager._process = _ProcessStub(pid=7777)

    async def _healthy() -> bool:
        return True

    monkeypatch.setattr(manager, "health_check", _healthy)
    monkeypatch.setattr(manager, "_resolve_listener_pid", lambda _port: 8888)

    result = await manager._wait_until_ready(timeout=0.2)

    assert result.ready is False
    assert result.reason == "listener_pid_mismatch"
    assert result.listener_pid == 8888


@pytest.mark.asyncio
async def test_start_restarts_when_startup_context_changed(tmp_path, monkeypatch: pytest.MonkeyPatch):
    manager = OpenCodeManager()
    workspace = tmp_path
    manager._status = OpenCodeStatus.RUNNING
    manager._workspace_path = workspace
    manager._startup_context = {"workspace_kind": "workbench-general", "project_id": "p1"}
    manager._instruction_policy = {}

    stop_called = {"value": False}

    async def _fake_stop_locked() -> None:
        stop_called["value"] = True
        manager._status = OpenCodeStatus.STOPPED

    monkeypatch.setattr(manager, "_stop_locked", _fake_stop_locked)
    monkeypatch.setattr(Config, "get_opencode_binary", staticmethod(lambda: None))

    ok = await manager.start(
        str(workspace),
        startup_context={"workspace_kind": "plugin-dev", "plugin_id": "com.demo.plugin"},
    )

    assert stop_called["value"] is True
    assert ok is False


@pytest.mark.asyncio
async def test_start_restarts_with_new_port_when_workspace_changes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    manager = OpenCodeManager()
    current_workspace = tmp_path / "old"
    next_workspace = tmp_path / "new"
    current_workspace.mkdir()
    next_workspace.mkdir()
    binary = tmp_path / "opencode"
    binary.write_text("", encoding="utf-8")
    manager._status = OpenCodeStatus.RUNNING
    manager._workspace_path = current_workspace
    manager._runtime_port = 4100
    manager._startup_context = {"workspace_kind": "plugin-dev", "plugin_id": "com.demo.old"}
    manager._instruction_policy = {}
    process = _ProcessStub(pid=9876)
    captured: dict[str, object] = {"stop_called": False}

    async def _fake_stop_locked() -> None:
        captured["stop_called"] = True
        manager._status = OpenCodeStatus.STOPPED
        manager._process = None
        manager._runtime_port = None

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs["cwd"]
        return process

    async def _fake_build_baseline_config():
        return {"server": {"port": manager.port}}

    async def _fake_wait_until_ready(timeout: float) -> OpenCodeReadyResult:
        return OpenCodeReadyResult(ready=True, listener_pid=process.pid)

    monkeypatch.setattr(Config, "get_opencode_binary", staticmethod(lambda: binary))
    monkeypatch.setattr(opencode_manager_module, "get_opencode_rules_service", lambda: _RulesServiceStub())
    monkeypatch.setattr(opencode_manager_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec)
    monkeypatch.setattr(manager, "_clear_quarantine_if_needed", lambda _binary: None)
    monkeypatch.setattr(manager, "_ensure_health_loop", lambda: None)
    monkeypatch.setattr(manager, "_allocate_runtime_port", lambda: 55234)
    monkeypatch.setattr(manager, "_build_baseline_config", _fake_build_baseline_config)
    monkeypatch.setattr(manager, "_wait_until_ready", _fake_wait_until_ready)
    monkeypatch.setattr(manager, "_stop_locked", _fake_stop_locked)

    ok = await manager.start(
        str(next_workspace),
        startup_context={"workspace_kind": "plugin-dev", "plugin_id": "com.demo.new"},
    )

    assert ok is True
    assert captured["stop_called"] is True
    assert captured["cwd"] == str(next_workspace)
    assert "55234" in captured["cmd"]
    assert manager.port == 55234
    assert manager.workspace_path == str(next_workspace)
    assert manager.startup_context["plugin_id"] == "com.demo.new"
