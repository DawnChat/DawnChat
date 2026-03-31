import pytest

from app.config import Config
from app.services.opencode_manager import OpenCodeManager, OpenCodeStatus


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
