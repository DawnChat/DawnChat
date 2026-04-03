from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import UploadFile

_MODULE_PATH = (
    Path(__file__).resolve().parents[4]
    / "app"
    / "plugins"
    / "application"
    / "plugin_agent_attachment_application_service.py"
)
_SPEC = importlib.util.spec_from_file_location("plugin_agent_attachment_application_service", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
PluginAgentAttachmentApplicationService = _MODULE.PluginAgentAttachmentApplicationService


def _build_service(plugin_root: Path, max_bytes: int = 1024) -> PluginAgentAttachmentApplicationService:
    return PluginAgentAttachmentApplicationService(
        get_plugin_path=lambda _plugin_id: str(plugin_root),
        uploads_dir_name="user-uploads",
        max_bytes=max_bytes,
    )


@pytest.mark.asyncio
async def test_save_upload_success_returns_relative_path(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir(parents=True)
    service = _build_service(plugin_root, max_bytes=4096)
    upload = UploadFile(filename="note.txt", file=BytesIO(b"hello"))

    payload = await service.save_upload("com.demo.app", upload)

    assert payload["plugin_id"] == "com.demo.app"
    assert payload["filename"] == "note.txt"
    assert payload["stored_path"] == "user-uploads/note.txt"
    assert payload["size_bytes"] == 5
    assert (plugin_root / "user-uploads" / "note.txt").read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_save_upload_rejects_oversized_file(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir(parents=True)
    service = _build_service(plugin_root, max_bytes=4)
    upload = UploadFile(filename="big.bin", file=BytesIO(b"12345"))

    with pytest.raises(ValueError) as exc:
        await service.save_upload("com.demo.app", upload)

    assert "max size" in str(exc.value)
    assert not (plugin_root / "user-uploads" / "big.bin").exists()


@pytest.mark.asyncio
async def test_save_upload_sanitizes_filename(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugin"
    plugin_root.mkdir(parents=True)
    service = _build_service(plugin_root)
    upload = UploadFile(filename="../unsafe name?.txt", file=BytesIO(b"ok"))

    payload = await service.save_upload("com.demo.app", upload)

    assert payload["filename"] == "unsafe_name_.txt"
    assert payload["stored_path"] == "user-uploads/unsafe_name_.txt"


@pytest.mark.asyncio
async def test_save_upload_plugin_missing_raises_not_found(tmp_path: Path) -> None:
    service = PluginAgentAttachmentApplicationService(
        get_plugin_path=lambda _plugin_id: str(tmp_path / "missing"),
        uploads_dir_name="user-uploads",
        max_bytes=1024,
    )
    upload = UploadFile(filename="a.txt", file=BytesIO(b"x"))

    with pytest.raises(FileNotFoundError):
        await service.save_upload("com.demo.app", upload)
