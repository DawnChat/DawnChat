from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from threading import Lock
from typing import Any, Optional

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("plugin_log_service")


@dataclass(slots=True)
class PluginLogEntry:
    level: str
    message: str
    timestamp: Optional[str] = None
    data: Optional[Any] = None


class PluginLogService:
    def __init__(self) -> None:
        self._write_lock = Lock()
        self._max_session_index_items = 50
        self._reserved_context_keys = {"plugin_id", "mode", "source", "session_id", "request_id"}

    def get_main_log_dir(self) -> Path:
        log_dir = Config.LOGS_DIR / "plugins"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def get_main_log_path(self, plugin_id: str) -> Path:
        path = self.get_main_log_dir() / f"{plugin_id}.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.touch()
        try:
            self._ensure_debug_mirror_file(plugin_id)
        except Exception:
            logger.debug("skip debug log mirror setup for plugin=%s", plugin_id, exc_info=True)
        return path

    def get_debug_log_dir(self, plugin_id: str) -> Path:
        root = self.resolve_plugin_root(plugin_id)
        debug_dir = root / ".debug" / "log"
        debug_dir.mkdir(parents=True, exist_ok=True)
        return debug_dir

    def get_debug_log_path(self, plugin_id: str) -> Path:
        return self.get_debug_log_dir(plugin_id) / f"{plugin_id}.log"

    def get_session_log_path(self, plugin_id: str, *, mode: str, session_id: str) -> Path:
        safe_mode = self._sanitize_segment(mode) or "preview"
        safe_session = self._normalize_session_id(mode=safe_mode, session_id=session_id)
        if not safe_session:
            raise RuntimeError("invalid session id")
        return self.get_debug_log_dir(plugin_id) / f"{safe_mode}-{safe_session}.log"

    def get_sessions_index_path(self, plugin_id: str) -> Path:
        return self.get_debug_log_dir(plugin_id) / "sessions.json"

    def append_entries(
        self,
        plugin_id: str,
        entries: list[PluginLogEntry],
        *,
        mode: str,
        source: str,
        request_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
        session_id: str = "",
    ) -> int:
        if not entries:
            return 0
        main_path = self.get_main_log_path(plugin_id)
        debug_path: Optional[Path] = None
        normalized_session_id = ""
        safe_mode = self._sanitize_segment(mode) or "preview"
        if session_id.strip():
            normalized_session_id = self._normalize_session_id(mode=safe_mode, session_id=session_id)
        try:
            debug_path = self.get_debug_log_path(plugin_id)
            self._ensure_debug_mirror_file(plugin_id)
        except Exception:
            debug_path = None
        authoritative_context = {
            "plugin_id": plugin_id,
            "mode": mode,
            "source": source,
            "session_id": normalized_session_id,
            "request_id": request_id,
        }
        conflict_entries = 0
        lines: list[str] = []
        for entry in entries:
            safe_metadata, safe_data, context_conflicts = self._sanitize_context_override(
                metadata=metadata,
                data=entry.data,
                authoritative_context=authoritative_context,
            )
            if context_conflicts:
                conflict_entries += 1
            lines.append(
                self._format_line(
                    level=entry.level,
                    message=entry.message,
                    timestamp=entry.timestamp,
                    mode=mode,
                    source=source,
                    session_id=normalized_session_id,
                    request_id=request_id,
                    data=safe_data,
                    metadata=safe_metadata,
                    context_conflicts=context_conflicts if context_conflicts else None,
                )
            )
        payload = "".join(lines)
        session_path: Optional[Path] = None
        if normalized_session_id:
            try:
                session_path = self.get_session_log_path(plugin_id, mode=mode, session_id=normalized_session_id)
            except Exception:
                session_path = None
        with self._write_lock:
            with open(main_path, "a", encoding="utf-8") as out:
                out.write(payload)
            if debug_path is not None:
                with open(debug_path, "a", encoding="utf-8") as mirror:
                    mirror.write(payload)
            if session_path is not None:
                with open(session_path, "a", encoding="utf-8") as session_file:
                    session_file.write(payload)
                try:
                    self._update_sessions_index(
                        plugin_id,
                        mode=mode,
                        source=source,
                        session_id=normalized_session_id,
                        entries_count=len(entries),
                    )
                except Exception:
                    logger.warning("update sessions index failed: plugin=%s", plugin_id, exc_info=True)
        if conflict_entries > 0:
            logger.warning(
                "plugin log context override blocked: plugin=%s mode=%s source=%s conflicts=%s",
                plugin_id,
                mode,
                source,
                conflict_entries,
            )
        return len(entries)

    def resolve_plugin_root(self, plugin_id: str) -> Path:
        from .manager import get_plugin_manager

        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if not plugin or not plugin.manifest.plugin_path:
            raise RuntimeError(f"plugin root not found: {plugin_id}")
        root = Path(plugin.manifest.plugin_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise RuntimeError(f"invalid plugin root: {root}")
        return root

    def _ensure_debug_mirror_file(self, plugin_id: str) -> None:
        debug_path = self.get_debug_log_path(plugin_id)
        if debug_path.exists():
            if debug_path.is_symlink():
                try:
                    debug_path.unlink()
                    debug_path.touch(exist_ok=True)
                except Exception:
                    logger.warning(
                        "replace debug log symlink failed: plugin=%s path=%s",
                        plugin_id,
                        debug_path,
                        exc_info=True,
                    )
            return
        try:
            debug_path.touch(exist_ok=True)
        except Exception:
            logger.warning("create debug log file failed: plugin=%s path=%s", plugin_id, debug_path, exc_info=True)

    @staticmethod
    def _format_line(
        *,
        level: str,
        message: str,
        timestamp: Optional[str],
        mode: str,
        source: str,
        session_id: str,
        request_id: str,
        data: Any,
        metadata: Optional[dict[str, Any]],
        context_conflicts: Optional[dict[str, Any]] = None,
    ) -> str:
        ts = str(timestamp or datetime.now().isoformat())
        lvl = str(level or "INFO").upper()
        base = f"[plugin-log {ts}] [{mode}] [{source}] [{lvl}]"
        if session_id:
            base += f" [session={session_id}]"
        if request_id:
            base += f" [request={request_id}]"
        base += f" {message}"
        payload: dict[str, Any] = {}
        if metadata:
            payload["metadata"] = metadata
        if data is not None:
            payload["data"] = data
        if context_conflicts:
            payload["context_conflicts"] = context_conflicts
        if payload:
            try:
                base += f" {json.dumps(payload, ensure_ascii=False, default=str)}"
            except Exception:
                base += f" {str(payload)}"
        return base + "\n"

    def _sanitize_context_override(
        self,
        *,
        metadata: Optional[dict[str, Any]],
        data: Any,
        authoritative_context: dict[str, str],
    ) -> tuple[Optional[dict[str, Any]], Any, dict[str, Any]]:
        safe_metadata, metadata_conflicts = self._strip_reserved_keys(
            raw=metadata,
            authoritative_context=authoritative_context,
        )
        safe_data, data_conflicts = self._strip_reserved_keys(
            raw=data if isinstance(data, dict) else None,
            authoritative_context=authoritative_context,
        )
        conflicts: dict[str, Any] = {}
        if metadata_conflicts:
            conflicts["metadata"] = metadata_conflicts
        if data_conflicts:
            conflicts["data"] = data_conflicts
        if not isinstance(data, dict):
            safe_data = data
        return safe_metadata, safe_data, conflicts

    def _strip_reserved_keys(
        self,
        *,
        raw: Optional[dict[str, Any]],
        authoritative_context: dict[str, str],
    ) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
        if not isinstance(raw, dict):
            return raw, {}
        cleaned: dict[str, Any] = {}
        conflicts: dict[str, Any] = {}
        for key, value in raw.items():
            if key in self._reserved_context_keys:
                normalized_authority = str(authoritative_context.get(key, ""))
                normalized_user = str(value)
                if normalized_user != normalized_authority:
                    conflicts[key] = {"system": normalized_authority, "user": normalized_user}
                # Always keep system-owned context out of user payload.
                continue
            cleaned[key] = value
        return cleaned, conflicts

    def _update_sessions_index(
        self,
        plugin_id: str,
        *,
        mode: str,
        source: str,
        session_id: str,
        entries_count: int,
    ) -> None:
        safe_session = self._sanitize_segment(session_id)
        if not safe_session:
            return
        safe_mode = self._sanitize_segment(mode) or "preview"
        safe_session = self._normalize_session_id(mode=safe_mode, session_id=safe_session)
        index_path = self.get_sessions_index_path(plugin_id)
        payload = self._read_sessions_index(index_path)
        now = datetime.now().isoformat()
        sessions = payload.get("sessions", [])
        found: Optional[dict[str, Any]] = None
        for item in sessions:
            if str(item.get("session_id") or "") == safe_session:
                found = item
                break
        if found is None:
            found = {
                "session_id": safe_session,
                "mode": str(mode or safe_mode),
                "started_at": now,
                "last_seen_at": now,
                "entries_count": max(0, int(entries_count)),
                "last_source": str(source or ""),
                "log_file": f"{safe_mode}-{safe_session}.log",
            }
            sessions.insert(0, found)
        else:
            found["mode"] = str(mode or found.get("mode") or safe_mode)
            found["last_seen_at"] = now
            found["entries_count"] = int(found.get("entries_count") or 0) + max(0, int(entries_count))
            found["last_source"] = str(source or found.get("last_source") or "")
            found["log_file"] = f"{safe_mode}-{safe_session}.log"
            sessions = [item for item in sessions if str(item.get("session_id") or "") != safe_session]
            sessions.insert(0, found)
        payload["version"] = 1
        payload["updated_at"] = now
        payload["sessions"] = sessions[: self._max_session_index_items]
        index_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _read_sessions_index(index_path: Path) -> dict[str, Any]:
        if not index_path.exists():
            return {"version": 1, "updated_at": "", "sessions": []}
        try:
            parsed = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"version": 1, "updated_at": "", "sessions": []}
        if not isinstance(parsed, dict):
            return {"version": 1, "updated_at": "", "sessions": []}
        sessions = parsed.get("sessions")
        if not isinstance(sessions, list):
            sessions = []
        return {
            "version": int(parsed.get("version") or 1),
            "updated_at": str(parsed.get("updated_at") or ""),
            "sessions": [item for item in sessions if isinstance(item, dict)],
        }

    @staticmethod
    def _sanitize_segment(raw: str) -> str:
        value = str(raw or "").strip()
        if not value:
            return ""
        allowed = []
        for ch in value:
            if ch.isalnum() or ch in ("-", "_", "."):
                allowed.append(ch)
            else:
                allowed.append("_")
        return "".join(allowed)[:96].strip("._-")

    def _normalize_session_id(self, *, mode: str, session_id: str) -> str:
        safe_mode = self._sanitize_segment(mode) or "preview"
        safe_session = self._sanitize_segment(session_id)
        if not safe_session:
            return ""
        mode_prefix = f"{safe_mode}-"
        while safe_session.startswith(mode_prefix):
            safe_session = safe_session[len(mode_prefix):]
        return safe_session


_plugin_log_service: Optional[PluginLogService] = None


def get_plugin_log_service() -> PluginLogService:
    global _plugin_log_service
    if _plugin_log_service is None:
        _plugin_log_service = PluginLogService()
    return _plugin_log_service
