import importlib
import sys
import types

from fastapi import HTTPException
import pytest

voice_stub = types.ModuleType("app.voice")
voice_stub.get_tts_runtime_service = lambda: types.SimpleNamespace(get_plugin_runtime_state=lambda _plugin_id: {})
sys.modules.setdefault("app.voice", voice_stub)

plugins_routes = importlib.import_module("app.api.plugins_routes")


class _DisplayNameManagerDouble:
    def __init__(self, *, plugin_exists: bool = True, error: Exception | None = None) -> None:
        self.plugin_exists = plugin_exists
        self.error = error
        self.calls: list[tuple[str, str]] = []

    async def ensure_initialized(self) -> bool:
        return True

    def get_plugin_snapshot(self, plugin_id: str):
        if not self.plugin_exists:
            return None
        return {"id": plugin_id}

    def update_plugin_display_name(self, plugin_id: str, name: str) -> dict:
        if self.error is not None:
            raise self.error
        self.calls.append((plugin_id, name))
        return {"plugin_id": plugin_id, "name": name.strip()}


@pytest.mark.asyncio
async def test_update_plugin_display_name_success(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _DisplayNameManagerDouble()
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    payload = await plugins_routes.update_plugin_display_name(
        "com.demo.app",
        plugins_routes.PluginDisplayNameUpdateRequest(name="Demo App"),
    )

    assert payload["status"] == "success"
    assert payload["plugin_id"] == "com.demo.app"
    assert payload["name"] == "Demo App"
    assert manager.calls == [("com.demo.app", "Demo App")]


@pytest.mark.asyncio
async def test_update_plugin_display_name_returns_404_when_plugin_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _DisplayNameManagerDouble(plugin_exists=False)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.update_plugin_display_name(
            "com.demo.app",
            plugins_routes.PluginDisplayNameUpdateRequest(name="Demo App"),
        )

    assert exc.value.status_code == 404
    assert "Plugin not found" in str(exc.value.detail)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (ValueError("Plugin name cannot be empty"), 400),
        (RuntimeError("Official plugin display name cannot be modified"), 400),
        (FileNotFoundError("Plugin manifest not found: com.demo.app"), 404),
    ],
)
async def test_update_plugin_display_name_maps_domain_errors(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
) -> None:
    manager = _DisplayNameManagerDouble(error=error)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.update_plugin_display_name(
            "com.demo.app",
            plugins_routes.PluginDisplayNameUpdateRequest(name="Demo App"),
        )

    assert exc.value.status_code == status_code
    assert str(error) in str(exc.value.detail)
