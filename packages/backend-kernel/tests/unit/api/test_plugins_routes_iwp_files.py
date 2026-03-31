import importlib
import sys
import types

import pytest
from fastapi import HTTPException

voice_stub = types.ModuleType("app.voice")
voice_stub.get_tts_runtime_service = lambda: types.SimpleNamespace(get_plugin_runtime_state=lambda _plugin_id: {})
sys.modules.setdefault("app.voice", voice_stub)

plugins_routes = importlib.import_module("app.api.plugins_routes")


class _IwpFilesManagerDouble:
    def __init__(self, *, plugin_exists: bool = True, error: Exception | None = None) -> None:
        self.plugin_exists = plugin_exists
        self.error = error

    async def ensure_initialized(self) -> bool:
        return True

    def get_plugin_snapshot(self, plugin_id: str):
        if not self.plugin_exists:
            return None
        return {"id": plugin_id}

    def list_iwp_markdown_files(self, plugin_id: str) -> dict:
        if self.error is not None:
            raise self.error
        return {
            "iwp_root": "InstructWare.iw",
            "files": [
                {
                    "path": "views/pages/home.md",
                    "name": "home.md",
                    "size": 123,
                    "updated_at": "2026-03-28T00:00:00",
                }
            ],
        }


@pytest.mark.asyncio
async def test_list_plugin_iwp_files_returns_404_when_plugin_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _IwpFilesManagerDouble(plugin_exists=False)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.list_plugin_iwp_files("com.demo.app")

    assert exc.value.status_code == 404
    assert "Plugin not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_plugin_iwp_files_returns_400_when_iwp_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _IwpFilesManagerDouble(error=RuntimeError("InstructWare.iw not found for plugin: com.demo.app"))
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.list_plugin_iwp_files("com.demo.app")

    assert exc.value.status_code == 400
    assert "InstructWare.iw not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_list_plugin_iwp_files_returns_payload_when_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _IwpFilesManagerDouble()
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    payload = await plugins_routes.list_plugin_iwp_files("com.demo.app")

    assert payload["status"] == "success"
    assert payload["plugin_id"] == "com.demo.app"
    assert payload["iwp_root"] == "InstructWare.iw"
    assert len(payload["files"]) == 1
    assert payload["files"][0]["path"] == "views/pages/home.md"
