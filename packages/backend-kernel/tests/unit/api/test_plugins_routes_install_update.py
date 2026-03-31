import pytest
from fastapi import HTTPException

from app.api import plugins_routes


class _RouteManagerDouble:
    def __init__(
        self,
        *,
        market_items: list[dict],
        check_update_result: bool = True,
    ) -> None:
        self.market_items = market_items
        self.check_update_result = check_update_result
        self.install_calls: list[dict] = []

    async def ensure_initialized(self) -> bool:
        return True

    async def list_market_plugins(self, force_refresh: bool = False) -> list[dict]:
        assert force_refresh is True
        return self.market_items

    async def install_from_package(
        self,
        *,
        plugin_id: str,
        version: str,
        package_url: str,
        package_sha256: str | None = None,
    ) -> None:
        self.install_calls.append(
            {
                "plugin_id": plugin_id,
                "version": version,
                "package_url": package_url,
                "package_sha256": package_sha256,
            }
        )

    def check_update(self, plugin_id: str, latest_version: str) -> bool:
        assert plugin_id
        assert latest_version
        return self.check_update_result


@pytest.mark.asyncio
async def test_install_plugin_selects_latest_version_when_request_version_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _RouteManagerDouble(
        market_items=[
            {"id": "com.demo.app", "version": "1.2.0", "package": {"url": "https://example.com/v120.zip"}},
            {"id": "com.demo.app", "version": "1.10.0", "package": {"url": "https://example.com/v1100.zip"}},
        ]
    )
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    response = await plugins_routes.install_plugin("com.demo.app", plugins_routes.PluginInstallRequest())

    assert response.version == "1.10.0"
    assert len(manager.install_calls) == 1
    assert manager.install_calls[0]["version"] == "1.10.0"
    assert manager.install_calls[0]["package_url"] == "https://example.com/v1100.zip"


@pytest.mark.asyncio
async def test_install_plugin_selects_requested_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _RouteManagerDouble(
        market_items=[
            {"id": "com.demo.app", "version": "1.2.0", "package": {"url": "https://example.com/v120.zip"}},
            {"id": "com.demo.app", "version": "1.10.0", "package": {"url": "https://example.com/v1100.zip"}},
        ]
    )
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    request = plugins_routes.PluginInstallRequest(version="1.2.0")
    response = await plugins_routes.install_plugin("com.demo.app", request)

    assert response.version == "1.2.0"
    assert len(manager.install_calls) == 1
    assert manager.install_calls[0]["version"] == "1.2.0"
    assert manager.install_calls[0]["package_url"] == "https://example.com/v120.zip"


@pytest.mark.asyncio
async def test_update_plugin_selects_latest_market_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _RouteManagerDouble(
        market_items=[
            {"id": "com.demo.app", "version": "1.2.0", "package": {"url": "https://example.com/v120.zip"}},
            {
                "id": "com.demo.app",
                "version": "1.10.0",
                "package": {"url": "https://example.com/v1100.zip", "sha256": "abc"},
            },
        ],
        check_update_result=True,
    )
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    response = await plugins_routes.update_plugin("com.demo.app")

    assert response.version == "1.10.0"
    assert len(manager.install_calls) == 1
    assert manager.install_calls[0]["version"] == "1.10.0"
    assert manager.install_calls[0]["package_sha256"] == "abc"


@pytest.mark.asyncio
async def test_update_plugin_raises_when_already_latest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _RouteManagerDouble(
        market_items=[
            {"id": "com.demo.app", "version": "1.10.0", "package": {"url": "https://example.com/v1100.zip"}},
        ],
        check_update_result=False,
    )
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.update_plugin("com.demo.app")

    assert exc.value.status_code == 400
    assert "already up to date" in str(exc.value.detail)
    assert manager.install_calls == []
