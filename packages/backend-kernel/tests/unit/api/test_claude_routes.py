import pytest
from fastapi import HTTPException

from app.api import claude_routes as routes
from app.services.claude_manager import ClaudeUnavailableError


class _ClaudeManagerStub:
    def __init__(self, start_ok: bool = True) -> None:
        self.start_ok = start_ok
        self.workspace_path = "/tmp/demo"
        self.status = type("Status", (), {"value": "running"})()

    async def start(self, **kwargs):
        return self.start_ok

    async def stop(self):
        return True

    async def get_health_payload(self):
        return {"state": "running", "healthy": True}

    async def get_runtime_diagnostics(self):
        return {"state": "running"}

    async def get_config_providers(self):
        return {"providers": [{"id": "anthropic", "configured": True, "available": True}]}

    async def patch_config(self, patch):
        return {"updated": True, "config": patch}

    async def list_agents(self):
        return {"agents": [{"id": "build"}]}


class _RulesStub:
    async def ensure_ready(self, force_refresh: bool = False):
        return {"enabled": True, "current_dir": "/tmp/rules"}

    def get_status(self):
        return {"enabled": True}

    def get_current_dir(self):
        return "/tmp/rules"


class _ResolveResult:
    workspace_path = "/tmp/workspace"
    startup_context = {"workspace_profile": {"mode": "plugin"}}
    instruction_policy = {"include_shared_rules": True}


@pytest.mark.asyncio
async def test_claude_health_rejects_when_feature_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.Config, "CLAUDE_ENABLED", False)
    with pytest.raises(HTTPException) as err:
        await routes.claude_health()
    assert err.value.status_code == 503


@pytest.mark.asyncio
async def test_start_claude_with_workspace_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.Config, "CLAUDE_ENABLED", True)
    monkeypatch.setattr(routes, "resolve_coding_agent_workspace", lambda **kwargs: _ResolveResult())
    monkeypatch.setattr(routes, "get_opencode_rules_service", lambda: _RulesStub())
    manager = _ClaudeManagerStub(start_ok=True)
    monkeypatch.setattr(routes, "get_claude_manager", lambda: manager)
    request = routes.StartWithWorkspaceRequest(workspace_kind="plugin-dev", plugin_id="com.demo.plugin")

    response = await routes.start_claude_with_workspace(request)

    assert response["status"] == "success"
    assert response["data"]["healthy"] is True
    assert response["data"]["rules"]["enabled"] is True


@pytest.mark.asyncio
async def test_claude_patch_config_rejects_empty_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.Config, "CLAUDE_ENABLED", True)
    monkeypatch.setattr(routes, "get_claude_manager", lambda: _ClaudeManagerStub())
    with pytest.raises(HTTPException) as err:
        await routes.claude_patch_config(routes.PatchConfigRequest())
    assert err.value.status_code == 400


@pytest.mark.asyncio
async def test_start_claude_with_workspace_returns_503_when_cli_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    class _UnavailableManager(_ClaudeManagerStub):
        async def start(self, **kwargs):
            raise ClaudeUnavailableError("本机未检测到 claude 命令，Claude Code 不可用")

    monkeypatch.setattr(routes.Config, "CLAUDE_ENABLED", True)
    monkeypatch.setattr(routes, "resolve_coding_agent_workspace", lambda **kwargs: _ResolveResult())
    monkeypatch.setattr(routes, "get_opencode_rules_service", lambda: _RulesStub())
    monkeypatch.setattr(routes, "get_claude_manager", lambda: _UnavailableManager())
    request = routes.StartWithWorkspaceRequest(workspace_kind="plugin-dev", plugin_id="com.demo.plugin")

    with pytest.raises(HTTPException) as err:
        await routes.start_claude_with_workspace(request)
    assert err.value.status_code == 503
