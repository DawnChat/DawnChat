from __future__ import annotations

import base64
import time
from typing import Any, Dict, Optional

import httpx

from app.config import Config
from app.services.network_service import NetworkService
from app.services.web_publish_service import WebPublishService
from app.utils.logger import get_logger

logger = get_logger("dawn_tts_edge_client")


class DawnTtsEdgeError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 0) -> None:
        super().__init__(message)
        self.code = str(code or "dawn_tts_error")
        self.status_code = int(status_code)


async def synthesize_to_mp3(*, access_token: str, text: str, voice: str) -> bytes:
    """
    POST Supabase Edge function dawn-tts; returns raw audio/mpeg bytes.
    """
    supabase_url = str(getattr(Config, "SUPABASE_URL", "") or "").strip()
    if not supabase_url:
        raise DawnTtsEdgeError("dawn_tts_supabase_url_missing", "SUPABASE_URL is not configured")

    fn = str(getattr(Config, "DAWN_TTS_FUNCTION_NAME", "dawn-tts") or "dawn-tts").strip() or "dawn-tts"
    url = f"{supabase_url.rstrip('/')}/functions/v1/{fn}"
    read_s = max(5.0, float(getattr(Config, "DAWN_TTS_EDGE_TIMEOUT_SECONDS", 90)))
    timeout = httpx.Timeout(connect=15.0, read=read_s, write=15.0, pool=10.0)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "apikey": WebPublishService._resolve_supabase_apikey(),
    }
    payload = {"text": text, "voice": voice}

    trust_env = await NetworkService.user_proxy_httpx_trust_env()
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=trust_env) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        logger.warning(
            "dawn-tts edge timeout url=%s elapsed_ms=%s read_timeout_s=%s phase=%s",
            url,
            elapsed_ms,
            read_s,
            type(exc).__name__,
        )
        raise DawnTtsEdgeError(
            "dawn_tts_timeout",
            f"edge request timed out after {elapsed_ms}ms",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("dawn-tts edge request failed url=%s err=%s", url, exc)
        raise DawnTtsEdgeError("dawn_tts_request_failed", str(exc)) from exc

    body = bytes(response.content or b"")
    parsed: Optional[Dict[str, Any]] = None
    try:
        parsed = response.json()
    except Exception:
        parsed = None

    if response.status_code == 401:
        raise DawnTtsEdgeError("dawn_tts_unauthorized", "unauthorized", status_code=401)
    if response.status_code == 429:
        raise DawnTtsEdgeError("dawn_tts_rate_limited", "rate limited", status_code=429)
    if response.status_code == 504:
        msg = ""
        if isinstance(parsed, dict):
            msg = str(parsed.get("message") or "").strip()
        raise DawnTtsEdgeError("dawn_tts_timeout", msg or "tts_timeout", status_code=504)
    if response.status_code >= 400:
        msg = ""
        code = f"dawn_tts_http_{response.status_code}"
        if isinstance(parsed, dict):
            msg = str(parsed.get("message") or parsed.get("detail") or "").strip()
            code = str(parsed.get("code") or code).strip() or code
        if not msg:
            msg = body.decode("utf-8", errors="replace").strip() or f"HTTP {response.status_code}"
        raise DawnTtsEdgeError(code, msg, status_code=response.status_code)

    content_type = str(response.headers.get("content-type") or "").lower()
    if "application/json" in content_type and parsed and isinstance(parsed, dict) and parsed.get("audio_base64"):
        raw = base64.b64decode(str(parsed.get("audio_base64") or ""), validate=False)
        if raw:
            return raw
    if not body:
        raise DawnTtsEdgeError("dawn_tts_empty_audio", "empty audio response")
    return body
