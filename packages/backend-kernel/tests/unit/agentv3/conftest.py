from __future__ import annotations

import pytest


class _OpenCodeRulesStub:
    async def ensure_ready(self, force_refresh: bool = False):
        return {"enabled": True, "forced": force_refresh}


@pytest.fixture(autouse=True)
def agentv3_isolation(monkeypatch: pytest.MonkeyPatch):
    """Fresh AgentV3 singleton per test; avoid opencode rules IO during create_session / run_coordinator."""
    import app.agentv3.service as agentv3_service

    agentv3_service._service_instance = None
    monkeypatch.setattr(
        "app.plugins.opencode_rules_service.get_opencode_rules_service",
        lambda: _OpenCodeRulesStub(),
    )
    yield
    agentv3_service._service_instance = None
