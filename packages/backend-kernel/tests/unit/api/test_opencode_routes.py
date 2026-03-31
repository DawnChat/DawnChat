from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import opencode_routes as routes


class _RulesServiceStub:
    async def ensure_ready(self, force_refresh: bool = False):
        return {"enabled": True, "forced": force_refresh}

    def get_status(self):
        return {"enabled": True}


class _ManagerFailStub:
    @property
    def last_start_failure(self):
        return {
            "reason": "health_timeout",
            "hint": "Failed to start server on port 4096",
        }

    async def start(self, **kwargs):
        return False

    async def get_health_payload(self):
        return {
            "status": "error",
            "healthy": False,
            "workspace_path": "/tmp/demo",
            "last_start_failure": self.last_start_failure,
        }


class _ManagerDiagStub:
    async def get_runtime_diagnostics(self):
        return {
            "health": {"status": "running", "healthy": True},
            "summary": {"suspected_blocker": "lsp"},
            "runtime_tail": [],
        }


@pytest.mark.asyncio
async def test_start_with_workspace_fail_returns_structured_detail(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        routes,
        "resolve_coding_agent_workspace",
        lambda **kwargs: SimpleNamespace(
            workspace_path="/tmp/demo",
            startup_context={"workspace_profile": {"app_type": "web"}},
            instruction_policy={},
        ),
    )
    monkeypatch.setattr(routes, "get_opencode_rules_service", lambda: _RulesServiceStub())
    monkeypatch.setattr(routes, "get_opencode_manager", lambda: _ManagerFailStub())
    request = routes.StartWithWorkspaceRequest(workspace_kind="plugin-dev", plugin_id="com.demo.app")

    with pytest.raises(HTTPException) as exc_info:
        await routes.start_opencode_with_workspace(request)

    assert exc_info.value.status_code == 500
    detail = exc_info.value.detail
    assert detail["message"] == "OpenCode 启动失败"
    assert detail["reason"] == "start_with_workspace_failed"
    assert detail["health"]["healthy"] is False
    assert detail["last_start_failure"]["reason"] == "health_timeout"


@pytest.mark.asyncio
async def test_opencode_diagnostics_success(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes, "get_opencode_manager", lambda: _ManagerDiagStub())

    payload = await routes.opencode_diagnostics()

    assert payload["status"] == "success"
    assert payload["data"]["summary"]["suspected_blocker"] == "lsp"
