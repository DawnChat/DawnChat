import pytest
from fastapi import HTTPException

from app.api import plugins_routes


class _FakeManager:
    def __init__(self, *, init_result: bool) -> None:
        self._init_result = init_result
        self.ensure_initialized_calls = 0

    async def ensure_initialized(self) -> bool:
        self.ensure_initialized_calls += 1
        return self._init_result

    def list_plugins(self) -> list[dict]:
        return [{"id": "com.demo.app", "state": "stopped"}]


@pytest.mark.asyncio
async def test_get_initialized_manager_success(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = _FakeManager(init_result=True)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: fake_manager)

    manager = await plugins_routes._get_initialized_manager()

    assert manager is fake_manager
    assert fake_manager.ensure_initialized_calls == 1


@pytest.mark.asyncio
async def test_get_initialized_manager_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = _FakeManager(init_result=False)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: fake_manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes._get_initialized_manager()

    assert exc.value.status_code == 500
    assert "initialization failed" in str(exc.value.detail)
    assert fake_manager.ensure_initialized_calls == 1


@pytest.mark.asyncio
async def test_list_plugins_uses_initialized_boundary(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_manager = _FakeManager(init_result=True)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: fake_manager)

    response = await plugins_routes.list_plugins()

    assert response.status == "success"
    assert response.count == 1
    assert fake_manager.ensure_initialized_calls == 1
