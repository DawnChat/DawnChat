from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Callable

from fastapi import UploadFile


class PluginAgentAttachmentApplicationService:
    _CHUNK_SIZE = 1024 * 1024
    _SAFE_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9._-]+")

    def __init__(
        self,
        *,
        get_plugin_path: Callable[[str], str | None],
        uploads_dir_name: str,
        max_bytes: int,
    ) -> None:
        self._get_plugin_path = get_plugin_path
        self._uploads_dir_name = str(uploads_dir_name or "user-uploads").strip() or "user-uploads"
        self._max_bytes = max(1, int(max_bytes))

    async def save_upload(self, plugin_id: str, file: UploadFile) -> dict[str, Any]:
        if file is None:
            raise ValueError("Attachment file is required")
        source_name = str(file.filename or "").strip()
        safe_filename = self._sanitize_filename(source_name)
        plugin_root = self._resolve_plugin_root(plugin_id)
        upload_root = self._resolve_upload_root(plugin_root)
        upload_root.mkdir(parents=True, exist_ok=True)
        target_path = self._allocate_target_path(upload_root, safe_filename)
        size_bytes = 0
        write_failed = False
        try:
            with target_path.open("wb") as output:
                while True:
                    chunk = await file.read(self._CHUNK_SIZE)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    if size_bytes > self._max_bytes:
                        raise ValueError(f"Attachment exceeds max size: {self._max_bytes} bytes")
                    output.write(chunk)
        except Exception:
            write_failed = True
            raise
        finally:
            await file.close()
            if write_failed and target_path.exists():
                target_path.unlink(missing_ok=True)

        relative_path = target_path.relative_to(plugin_root).as_posix()
        return {
            "plugin_id": plugin_id,
            "filename": target_path.name,
            "stored_path": relative_path,
            "size_bytes": size_bytes,
        }

    def _resolve_plugin_root(self, plugin_id: str) -> Path:
        plugin_path = self._get_plugin_path(plugin_id)
        if not plugin_path:
            raise FileNotFoundError(f"Plugin path not found: {plugin_id}")
        root = Path(plugin_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"Plugin source directory not found: {plugin_id}")
        return root

    def _resolve_upload_root(self, plugin_root: Path) -> Path:
        upload_root = (plugin_root / self._uploads_dir_name).resolve()
        try:
            upload_root.relative_to(plugin_root)
        except ValueError as err:
            raise ValueError("Invalid upload directory configuration") from err
        return upload_root

    def _allocate_target_path(self, upload_root: Path, filename: str) -> Path:
        base_name = Path(filename).stem
        suffix = Path(filename).suffix
        candidate = (upload_root / filename).resolve()
        index = 1
        while candidate.exists():
            candidate = (upload_root / f"{base_name}-{index}{suffix}").resolve()
            index += 1
        try:
            candidate.relative_to(upload_root)
        except ValueError as err:
            raise ValueError("Invalid upload target path") from err
        return candidate

    @classmethod
    def _sanitize_filename(cls, name: str) -> str:
        basename = Path(str(name or "").strip()).name
        if basename in {"", ".", ".."}:
            basename = "upload.bin"
        sanitized = cls._SAFE_NAME_PATTERN.sub("_", basename).strip("._")
        if not sanitized:
            sanitized = "upload.bin"
        return sanitized[:200]
