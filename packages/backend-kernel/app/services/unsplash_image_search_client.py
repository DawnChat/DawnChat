from __future__ import annotations

import time
from typing import Any, Dict, Optional

import httpx

from app.config import Config
from app.services.network_service import NetworkService
from app.services.web_publish_service import WebPublishService
from app.utils.logger import get_logger

logger = get_logger("unsplash_image_search_client")


class UnsplashImageSearchError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = int(status_code)


async def search_images_via_edge(
    *,
    access_token: str,
    keyword: str,
    max_results: int,
) -> Dict[str, Any]:
    """
    Call Supabase Edge Function `image-search` with the user's JWT.
    Returns parsed JSON on success (HTTP 200 and body.get("ok")).
    """
    supabase_url = str(getattr(Config, "SUPABASE_URL", "") or "").strip()
    if not supabase_url:
        raise UnsplashImageSearchError("supabase_url_missing", "SUPABASE_URL is not configured")

    fn = str(getattr(Config, "IMAGE_SEARCH_FUNCTION_NAME", "image-search") or "image-search").strip()
    url = f"{supabase_url.rstrip('/')}/functions/v1/{fn}"
    read_s = max(5.0, float(getattr(Config, "IMAGE_SEARCH_EDGE_TIMEOUT_SECONDS", 50)))
    timeout = httpx.Timeout(
        connect=15.0,
        read=read_s,
        write=15.0,
        pool=10.0,
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "apikey": WebPublishService._resolve_supabase_apikey(),
    }
    per_page = max(1, min(int(max_results), 30))
    payload = {"keyword": keyword, "max_results": per_page}

    # Align with settings UI: when proxy is enabled, NetworkService has set HTTP(S)_PROXY on the process.
    trust_env = await NetworkService.user_proxy_httpx_trust_env()

    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, trust_env=trust_env) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        # ConnectTimeout = TLS/TCP to Supabase; ReadTimeout = waiting for response body (Edge + upstream).
        logger.warning(
            "image-search edge timeout url=%s elapsed_ms=%s read_timeout_s=%s connect_timeout_s=15 "
            "httpx_timeout_phase=%s detail=%r",
            url,
            elapsed_ms,
            read_s,
            type(exc).__name__,
            str(exc) or getattr(exc, "args", ()),
        )
        raise UnsplashImageSearchError(
            "image_search_timeout",
            f"edge request timed out after {elapsed_ms}ms (phase={type(exc).__name__}, read_timeout_s={read_s})",
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("image-search edge request failed url=%s err=%s", url, exc)
        raise UnsplashImageSearchError("image_search_request_failed", str(exc)) from exc

    text = response.text
    parsed: Optional[Dict[str, Any]] = None
    try:
        parsed = response.json()
    except Exception:
        parsed = None

    if response.status_code == 429:
        raise UnsplashImageSearchError("image_search_rate_limited", "rate limited", status_code=429)
    if response.status_code >= 400:
        msg = ""
        code = f"image_search_http_{response.status_code}"
        if isinstance(parsed, dict):
            msg = str(parsed.get("message") or parsed.get("detail") or "").strip()
            code = str(parsed.get("code") or code).strip() or code
        if not msg:
            msg = text.strip() or f"HTTP {response.status_code}"
        logger.info(
            "image-search edge error status=%s code=%s",
            response.status_code,
            code,
        )
        raise UnsplashImageSearchError(code, msg, status_code=response.status_code)

    if not isinstance(parsed, dict) or not parsed.get("ok"):
        raise UnsplashImageSearchError("image_search_invalid_response", "invalid edge response")

    elapsed_ms = int((time.monotonic() - started) * 1000)
    logger.info(
        "image-search edge ok keyword=%s elapsed_ms=%s status=%s",
        keyword,
        elapsed_ms,
        response.status_code,
    )
    return parsed
