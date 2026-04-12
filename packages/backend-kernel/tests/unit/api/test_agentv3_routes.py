from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.api import agentv3_routes as routes


class _Service404Prompt:
    async def prompt(self, session_id: str, payload: dict):
        return None

    async def prompt_async(self, session_id: str, payload: dict):
        return False


class _ServiceMetaStub:
    def get_engine_meta(self):
        return {"engine": "agentv3", "version": "test", "capabilities": {"multi_session": True}}


@pytest.mark.asyncio
async def test_prompt_sync_404_when_no_message(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes, "get_agentv3_service", lambda: _Service404Prompt())
    with pytest.raises(HTTPException) as exc_info:
        await routes.prompt_sync("missing-session", routes.PromptRequest(parts=[{"type": "text", "text": "hi"}]))
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_prompt_async_404_when_service_returns_false(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes, "get_agentv3_service", lambda: _Service404Prompt())
    with pytest.raises(HTTPException) as exc_info:
        await routes.prompt_async("missing-session", routes.PromptRequest(parts=[{"type": "text", "text": "hi"}]))
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_engine_meta_returns_payload(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(routes, "get_agentv3_service", lambda: _ServiceMetaStub())
    payload = await routes.get_engine_meta()
    assert payload["engine"] == "agentv3"
    assert payload["version"] == "test"
