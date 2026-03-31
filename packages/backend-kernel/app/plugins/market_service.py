"""
Plugin market index service.

Fetches and caches plugins.json from remote.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx

from app.config import Config
from app.utils.logger import get_logger

from .versioning import is_version_newer

logger = get_logger("plugin_market_service")


class PluginMarketService:
    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._etags: dict[str, str] = {}
        self._last_fetch_at: Optional[datetime] = None
        self._ttl = timedelta(seconds=300)
        self._lock = asyncio.Lock()

    def _is_cache_fresh(self) -> bool:
        if self._last_fetch_at is None:
            return False
        return datetime.now(timezone.utc) - self._last_fetch_at < self._ttl

    async def fetch_index(self, force: bool = False) -> dict[str, Any]:
        async with self._lock:
            if not force and self._cache and self._is_cache_fresh():
                return self._cache

            urls: list[str] = [Config.PLUGIN_MARKET_INDEX_URL]
            for fallback in Config.PLUGIN_MARKET_INDEX_FALLBACK_URLS:
                if fallback and fallback not in urls:
                    urls.append(fallback)

            errors: list[str] = []
            for url in urls:
                headers: dict[str, str] = {}
                etag = self._etags.get(url)
                if etag:
                    headers["If-None-Match"] = etag
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    try:
                        response = await client.get(url, headers=headers)
                        if response.status_code == 304 and self._cache:
                            self._last_fetch_at = datetime.now(timezone.utc)
                            logger.info("plugin_market_index_not_modified source=%s", url)
                            return self._cache
                        response.raise_for_status()
                        payload = response.json()
                        if not isinstance(payload, dict):
                            raise ValueError("plugins.json root must be object")
                        plugins = payload.get("plugins")
                        if not isinstance(plugins, list):
                            raise ValueError("plugins.json missing plugins array")
                        self._cache = payload
                        response_etag = response.headers.get("ETag")
                        if response_etag:
                            self._etags[url] = response_etag
                        self._last_fetch_at = datetime.now(timezone.utc)
                        logger.info("plugin_market_index_loaded source=%s count=%s", url, len(plugins))
                        return self._cache
                    except Exception as e:
                        error_text = f"{url}: {type(e).__name__}({e!r})"
                        errors.append(error_text)
                        logger.warning("plugin_market_index_fetch_failed source=%s error=%s", url, error_text)

            if self._cache:
                logger.warning("plugin_market_all_sources_failed_use_cache errors=%s", "; ".join(errors))
                return self._cache

            logger.error("plugin_market_all_sources_failed_return_empty errors=%s", "; ".join(errors))
            self._cache = {
                "schema_version": "1.0.0",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "plugins": [],
            }
            self._last_fetch_at = datetime.now(timezone.utc)
            return self._cache

    async def list_plugins(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        data = await self.fetch_index(force=force_refresh)
        plugins = data.get("plugins", [])
        if not isinstance(plugins, list):
            return []
        return [p for p in plugins if isinstance(p, dict)]

    def merge_with_local(self, market_plugins: list[dict[str, Any]], local_plugins: list[dict[str, Any]]) -> list[dict[str, Any]]:
        local_map = {str(item.get("id")): item for item in local_plugins if item.get("id")}
        merged: list[dict[str, Any]] = []
        for market in market_plugins:
            plugin_id = str(market.get("id") or "")
            if not plugin_id:
                continue
            local = local_map.get(plugin_id)
            latest_version = str(market.get("version") or "")
            installed_version = str(local.get("version") or "") if local else ""
            action = "install"
            if local:
                action = "open" if local.get("state") == "running" else "installed"
                if latest_version and installed_version:
                    if is_version_newer(latest_version, installed_version):
                        action = "update"

            merged.append(
                {
                    **market,
                    "installed": bool(local),
                    "installed_version": installed_version or None,
                    "state": local.get("state") if local else "not_installed",
                    "action": action,
                    "source_type": local.get("source_type") if local else None,
                    "owner_user_id": local.get("owner_user_id") if local else None,
                    "owner_email": local.get("owner_email") if local else None,
                }
            )
        return merged


_plugin_market_service: Optional[PluginMarketService] = None


def get_plugin_market_service() -> PluginMarketService:
    global _plugin_market_service
    if _plugin_market_service is None:
        _plugin_market_service = PluginMarketService()
    return _plugin_market_service
