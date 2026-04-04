import importlib
from io import BytesIO
import sys
import types

from fastapi import HTTPException, UploadFile
from fastapi.dependencies import utils as fastapi_dep_utils
import pytest

fastapi_dep_utils.ensure_multipart_is_installed = lambda: None

voice_stub = types.ModuleType("app.voice")
voice_stub.get_tts_runtime_service = lambda: types.SimpleNamespace(get_plugin_runtime_state=lambda _plugin_id: {})
sys.modules.setdefault("app.voice", voice_stub)

plugins_routes = importlib.import_module("app.api.plugins_routes")


class _UploadManagerDouble:
    def __init__(self, *, plugin_exists: bool = True, save_error: Exception | None = None) -> None:
        self.plugin_exists = plugin_exists
        self.save_error = save_error

    async def ensure_initialized(self) -> bool:
        return True

    def get_plugin_snapshot(self, plugin_id: str):
        if not self.plugin_exists:
            return None
        return {"id": plugin_id}

    async def save_agent_attachment(self, plugin_id: str, file: UploadFile) -> dict:
        if self.save_error is not None:
            raise self.save_error
        content = await file.read()
        return {
            "plugin_id": plugin_id,
            "filename": file.filename,
            "stored_path": f"user-uploads/{file.filename}",
            "size_bytes": len(content),
        }


@pytest.mark.asyncio
async def test_upload_agent_attachment_returns_404_when_plugin_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _UploadManagerDouble(plugin_exists=False)
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.upload_agent_attachment(
            "com.demo.app",
            UploadFile(filename="a.txt", file=BytesIO(b"x")),
        )

    assert exc.value.status_code == 404
    assert "Plugin not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_upload_agent_attachment_returns_413_when_size_exceeded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _UploadManagerDouble(save_error=ValueError("Attachment exceeds max size: 10 bytes"))
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    with pytest.raises(HTTPException) as exc:
        await plugins_routes.upload_agent_attachment(
            "com.demo.app",
            UploadFile(filename="big.bin", file=BytesIO(b"x")),
        )

    assert exc.value.status_code == 413
    assert "max size" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_upload_agent_attachment_returns_payload_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _UploadManagerDouble()
    monkeypatch.setattr(plugins_routes, "get_plugin_manager", lambda: manager)

    payload = await plugins_routes.upload_agent_attachment(
        "com.demo.app",
        UploadFile(filename="report.pdf", file=BytesIO(b"abc")),
    )

    assert payload["status"] == "success"
    assert payload["plugin_id"] == "com.demo.app"
    assert payload["stored_path"] == "user-uploads/report.pdf"
    assert payload["size_bytes"] == 3
