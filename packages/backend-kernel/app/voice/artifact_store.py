from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

from app.config import Config


@dataclass(slots=True)
class _TaskArtifacts:
    files: Dict[int, Path] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class TtsArtifactStore:
    def __init__(self, base_dir: Path | None = None, ttl_seconds: int = 600) -> None:
        self._base_dir = base_dir or (Config.DATA_DIR / "tts" / "segments")
        self._ttl_seconds = max(30, int(ttl_seconds))
        self._tasks: Dict[str, _TaskArtifacts] = {}
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def register_task(self, task_id: str) -> None:
        self._tasks.setdefault(task_id, _TaskArtifacts())
        self._touch(task_id)

    def write_segment(self, task_id: str, seq: int, payload: bytes) -> Path:
        self.register_task(task_id)
        task_dir = self._base_dir / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        path = task_dir / f"{seq}.wav"
        path.write_bytes(payload)
        self._tasks[task_id].files[int(seq)] = path
        self._touch(task_id)
        return path

    def resolve_segment(self, task_id: str, seq: int) -> Path | None:
        task = self._tasks.get(task_id)
        if task is None:
            path = self._base_dir / task_id / f"{seq}.wav"
            return path if path.exists() else None
        cached_path = task.files.get(int(seq))
        if cached_path and cached_path.exists():
            return cached_path
        fallback = self._base_dir / task_id / f"{seq}.wav"
        return fallback if fallback.exists() else None

    def mark_completed(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.completed_at = datetime.utcnow()
        self._touch(task_id)

    def cleanup_expired(self) -> int:
        now = datetime.utcnow()
        expire_before = now - timedelta(seconds=self._ttl_seconds)
        deleted = 0
        for task_id, task in list(self._tasks.items()):
            ref = task.completed_at or task.updated_at
            if ref >= expire_before:
                continue
            deleted += self._remove_task(task_id)
        for path in self._base_dir.iterdir():
            if not path.is_dir():
                continue
            if path.name in self._tasks:
                continue
            try:
                ref_time = datetime.utcfromtimestamp(path.stat().st_mtime)
            except OSError:
                continue
            if ref_time < expire_before:
                deleted += self._remove_dir(path)
        return deleted

    def _remove_task(self, task_id: str) -> int:
        self._tasks.pop(task_id, None)
        return self._remove_dir(self._base_dir / task_id)

    @staticmethod
    def _remove_dir(path: Path) -> int:
        if not path.exists():
            return 0
        deleted = 0
        for child in path.glob("*"):
            try:
                child.unlink(missing_ok=True)
                deleted += 1
            except OSError:
                continue
        try:
            path.rmdir()
        except OSError:
            pass
        return deleted

    def _touch(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.updated_at = datetime.utcnow()


_tts_artifact_store: TtsArtifactStore | None = None


def get_tts_artifact_store() -> TtsArtifactStore:
    global _tts_artifact_store
    if _tts_artifact_store is None:
        _tts_artifact_store = TtsArtifactStore()
    return _tts_artifact_store
