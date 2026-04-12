from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, Optional

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("supabase_session_store")

_KERNEL_SESSION_FILENAME = "supabase_kernel_session.json"


class SupabaseSessionStore:
    """
    Persist a copy of the Supabase session for backend calls (e.g. Edge Functions).
    Refresh is performed only by the host frontend; this store never calls GoTrue.
    """

    def __init__(self) -> None:
        self._path = Config.DATA_DIR / _KERNEL_SESSION_FILENAME
        self._lock = asyncio.Lock()

    async def save(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            Config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            normalized = {
                "access_token": str(payload.get("access_token") or "").strip(),
                "refresh_token": str(payload.get("refresh_token") or "").strip(),
                "expires_at": payload.get("expires_at"),
                "supabase_user_id": str(payload.get("supabase_user_id") or "").strip() or None,
            }
            if not normalized["access_token"]:
                logger.warning("supabase session save skipped: empty access_token")
                return
            tmp = self._path.with_suffix(".json.tmp")
            body = json.dumps(normalized, ensure_ascii=True, indent=2, sort_keys=True)
            tmp.write_text(body, encoding="utf-8")
            tmp.replace(self._path)

    async def clear(self) -> None:
        async with self._lock:
            try:
                self._path.unlink(missing_ok=True)
            except OSError as err:
                logger.warning("supabase session clear failed: %s", err)

    async def get_usable_access_token(self) -> Optional[str]:
        async with self._lock:
            if not self._path.is_file():
                return None
            try:
                raw = self._path.read_text(encoding="utf-8")
                data = json.loads(raw)
            except (OSError, json.JSONDecodeError) as err:
                logger.warning("supabase session read failed: %s", err)
                return None
            if not isinstance(data, dict):
                return None
            token = str(data.get("access_token") or "").strip()
            if not token:
                return None
            exp = data.get("expires_at")
            if exp is None:
                return None
            try:
                exp_f = float(exp)
            except (TypeError, ValueError):
                return None
            skew = max(0.0, float(getattr(Config, "SUPABASE_ACCESS_SKEW_SECONDS", 90)))
            if time.time() >= exp_f - skew:
                return None
            return token


_store: Optional[SupabaseSessionStore] = None


def get_supabase_session_store() -> SupabaseSessionStore:
    global _store
    if _store is None:
        _store = SupabaseSessionStore()
    return _store
