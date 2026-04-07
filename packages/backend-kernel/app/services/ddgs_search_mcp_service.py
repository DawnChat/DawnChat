from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from app.config import Config
from app.utils.logger import get_logger

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - runtime dependency fallback
    DDGS = None  # type: ignore[assignment]

logger = get_logger("ddgs_search_mcp_service")


@dataclass(frozen=True, slots=True)
class DdgsToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass(slots=True)
class _CacheEntry:
    payload: Dict[str, Any]
    expires_at: float
    cached_at: str


class DdgsSearchMcpService:
    def __init__(self) -> None:
        self._cache_lock = asyncio.Lock()
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()

    def tool_definitions(self) -> List[DdgsToolDefinition]:
        search_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "region": {"type": "string", "description": "Region code, e.g. us-en"},
                "safesearch": {"type": "string", "enum": ["on", "moderate", "off"], "default": "moderate"},
                "timelimit": {"type": "string", "enum": ["d", "w", "m", "y"]},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": int(getattr(Config, "DDGS_SEARCH_MAX_RESULTS_LIMIT", 10)),
                    "default": int(getattr(Config, "DDGS_SEARCH_DEFAULT_MAX_RESULTS", 5)),
                },
            },
            "required": ["query"],
        }
        return [
            DdgsToolDefinition(
                name="dawnchat.search.text",
                description="Search text results from web search engines",
                input_schema=search_schema,
            ),
            DdgsToolDefinition(
                name="dawnchat.search.image",
                description="Search image results from web search engines",
                input_schema=search_schema,
            ),
            DdgsToolDefinition(
                name="dawnchat.search.video",
                description="Search video results from web search engines",
                input_schema=search_schema,
            ),
            DdgsToolDefinition(
                name="dawnchat.search.extract",
                description="Fetch URL content and extract it as markdown text",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "Target URL"},
                        "fmt": {
                            "type": "string",
                            "enum": ["text_markdown", "text_plain", "text_rich", "text"],
                            "default": "text_markdown",
                        },
                    },
                    "required": ["url"],
                },
            ),
        ]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        tool_name = str(name or "").strip()
        if tool_name not in {
            "dawnchat.search.text",
            "dawnchat.search.image",
            "dawnchat.search.video",
            "dawnchat.search.extract",
        }:
            return {"ok": False, "error_code": "tool_not_found", "message": f"unknown tool: {tool_name}"}
        if DDGS is None:
            return {
                "ok": False,
                "error_code": "ddgs_unavailable",
                "message": "ddgs package is not available",
            }
        try:
            normalized = self._validate_arguments(tool_name, arguments)
        except ValueError as err:
            return {"ok": False, "error_code": "invalid_arguments", "message": str(err)}

        ttl_seconds = self._resolve_ttl(tool_name)
        cache_key = self._build_cache_key(tool_name, normalized)
        cached_payload = await self._read_cache(cache_key, ttl_seconds)
        if cached_payload is not None:
            payload = dict(cached_payload)
            payload["cache_hit"] = True
            return {"ok": True, "data": payload}

        try:
            result_payload = await asyncio.to_thread(self._execute_ddgs_call, tool_name, normalized)
        except Exception as err:
            if self._is_no_results_error(err) and tool_name in {
                "dawnchat.search.text",
                "dawnchat.search.image",
                "dawnchat.search.video",
            }:
                logger.info("ddgs search no results tool=%s query=%s", tool_name, normalized.get("query"))
                return {
                    "ok": True,
                    "data": self._build_empty_search_payload(tool_name=tool_name, arguments=normalized),
                }
            logger.warning("ddgs search failed tool=%s error=%s", tool_name, err)
            return {"ok": False, "error_code": "ddgs_request_failed", "message": str(err)}

        result_payload["cache_hit"] = False
        await self._write_cache(cache_key, result_payload, ttl_seconds)
        return {"ok": True, "data": result_payload}

    def _execute_ddgs_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if DDGS is None:
            raise RuntimeError("ddgs package is not available")
        timeout = max(1, int(getattr(Config, "DDGS_TIMEOUT_SECONDS", 8)))
        client = DDGS(timeout=timeout)
        if tool_name == "dawnchat.search.text":
            items = client.text(
                query=arguments["query"],
                region=arguments["region"],
                safesearch=arguments["safesearch"],
                timelimit=arguments.get("timelimit"),
                max_results=arguments["max_results"],
                backend="auto",
            )
            return {
                "tool": tool_name,
                "query": arguments["query"],
                "region": arguments["region"],
                "max_results": arguments["max_results"],
                "items": self._normalize_text_items(items),
            }
        if tool_name == "dawnchat.search.image":
            items, fallback_used, effective_region, effective_safesearch = self._execute_ddgs_image_with_fallback(
                client=client,
                arguments=arguments,
            )
            return {
                "tool": tool_name,
                "query": arguments["query"],
                "region": effective_region,
                "requested_region": arguments["region"],
                "safesearch": effective_safesearch,
                "requested_safesearch": arguments["safesearch"],
                "max_results": arguments["max_results"],
                "items": self._normalize_image_items(items),
                "fallback_used": fallback_used,
            }
        if tool_name == "dawnchat.search.video":
            video_timelimit = arguments.get("timelimit")
            if video_timelimit not in {"d", "w", "m", None}:
                video_timelimit = None
            items = client.videos(
                query=arguments["query"],
                region=arguments["region"],
                safesearch=arguments["safesearch"],
                timelimit=video_timelimit,
                max_results=arguments["max_results"],
                backend="auto",
            )
            return {
                "tool": tool_name,
                "query": arguments["query"],
                "region": arguments["region"],
                "max_results": arguments["max_results"],
                "items": self._normalize_video_items(items),
            }
        extracted = client.extract(arguments["url"], fmt=arguments["fmt"])
        content = extracted.get("content") if isinstance(extracted, dict) else ""
        if not isinstance(content, str):
            content = str(content or "")
        return {
            "tool": tool_name,
            "url": arguments["url"],
            "fmt": arguments["fmt"],
            "content": content,
            "content_length": len(content),
        }

    @staticmethod
    def _validate_arguments(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == "dawnchat.search.extract":
            url = str(arguments.get("url") or "").strip()
            if not url:
                raise ValueError("url is required")
            parsed = urlparse(url)
            if parsed.scheme not in {"http", "https"}:
                raise ValueError("url must start with http:// or https://")
            fmt = str(arguments.get("fmt") or "text_markdown").strip()
            if fmt not in {"text_markdown", "text_plain", "text_rich", "text"}:
                raise ValueError("fmt must be one of: text_markdown, text_plain, text_rich, text")
            return {"url": url, "fmt": fmt}

        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required")
        if len(query) > 300:
            raise ValueError("query is too long, maximum length is 300")
        region = str(arguments.get("region") or "us-en").strip() or "us-en"
        safesearch = str(arguments.get("safesearch") or "moderate").strip().lower()
        if safesearch not in {"on", "moderate", "off"}:
            raise ValueError("safesearch must be one of: on, moderate, off")
        timelimit_raw = arguments.get("timelimit")
        timelimit: Optional[str] = None
        if timelimit_raw is not None:
            timelimit = str(timelimit_raw).strip().lower()
            if timelimit not in {"d", "w", "m", "y"}:
                raise ValueError("timelimit must be one of: d, w, m, y")
        max_default = int(getattr(Config, "DDGS_SEARCH_DEFAULT_MAX_RESULTS", 5))
        max_limit = int(getattr(Config, "DDGS_SEARCH_MAX_RESULTS_LIMIT", 10))
        try:
            max_results = int(arguments.get("max_results") or max_default)
        except (TypeError, ValueError):
            raise ValueError("max_results must be an integer") from None
        max_results = max(1, min(max_results, max(1, max_limit)))
        return {
            "query": query,
            "region": region,
            "safesearch": safesearch,
            "timelimit": timelimit,
            "max_results": max_results,
        }

    @staticmethod
    def _normalize_text_items(items: Any) -> List[Dict[str, Any]]:
        rows = items if isinstance(items, list) else []
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "title": str(row.get("title") or ""),
                    "url": str(row.get("href") or row.get("url") or ""),
                    "snippet": str(row.get("body") or ""),
                }
            )
        return normalized

    @staticmethod
    def _normalize_image_items(items: Any) -> List[Dict[str, Any]]:
        rows = items if isinstance(items, list) else []
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "title": str(row.get("title") or ""),
                    "url": str(row.get("url") or row.get("image") or ""),
                    "thumbnail": str(row.get("thumbnail") or ""),
                    "source": str(row.get("source") or ""),
                    "width": row.get("width"),
                    "height": row.get("height"),
                }
            )
        return normalized

    @staticmethod
    def _normalize_video_items(items: Any) -> List[Dict[str, Any]]:
        rows = items if isinstance(items, list) else []
        normalized: List[Dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            normalized.append(
                {
                    "title": str(row.get("title") or ""),
                    "url": str(row.get("content") or row.get("url") or ""),
                    "description": str(row.get("description") or ""),
                    "duration": str(row.get("duration") or ""),
                    "publisher": str(row.get("publisher") or ""),
                }
            )
        return normalized

    def _execute_ddgs_image_with_fallback(
        self,
        *,
        client: Any,
        arguments: Dict[str, Any],
    ) -> tuple[list[dict[str, Any]], bool, str, str]:
        query = arguments["query"]
        region = arguments["region"]
        safesearch = arguments["safesearch"]
        timelimit = arguments.get("timelimit")
        max_results = arguments["max_results"]

        try:
            primary = client.images(
                query=query,
                region=region,
                safesearch=safesearch,
                timelimit=timelimit,
                max_results=max_results,
                backend="auto",
            )
            if isinstance(primary, list) and primary:
                return primary, False, region, safesearch
        except Exception as err:
            if not self._is_no_results_error(err):
                raise

        fallback_region = str(getattr(Config, "DDGS_IMAGE_FALLBACK_REGION", "wt-wt"))
        fallback_safesearch = str(getattr(Config, "DDGS_IMAGE_FALLBACK_SAFESEARCH", "moderate"))
        if fallback_region == region and fallback_safesearch == safesearch:
            return [], False, region, safesearch

        fallback = client.images(
            query=query,
            region=fallback_region,
            safesearch=fallback_safesearch,
            timelimit=timelimit,
            max_results=max_results,
            backend="auto",
        )
        return (fallback if isinstance(fallback, list) else []), True, fallback_region, fallback_safesearch

    @staticmethod
    def _build_cache_key(tool_name: str, arguments: Dict[str, Any]) -> str:
        encoded = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(f"{tool_name}:{encoded}".encode("utf-8")).hexdigest()
        return f"{tool_name}:{digest}"

    @staticmethod
    def _resolve_ttl(tool_name: str) -> int:
        if tool_name == "dawnchat.search.extract":
            return max(1, int(getattr(Config, "DDGS_EXTRACT_CACHE_TTL_SECONDS", 600)))
        return max(1, int(getattr(Config, "DDGS_SEARCH_CACHE_TTL_SECONDS", 300)))

    @staticmethod
    def _is_no_results_error(err: Exception) -> bool:
        text = str(err or "").strip().lower()
        return "no results found" in text

    @staticmethod
    def _build_empty_search_payload(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "tool": tool_name,
            "query": str(arguments.get("query") or ""),
            "region": str(arguments.get("region") or "us-en"),
            "max_results": int(arguments.get("max_results") or 0),
            "items": [],
            "no_results": True,
        }

    async def _read_cache(self, key: str, ttl_seconds: int) -> Optional[Dict[str, Any]]:
        if not bool(getattr(Config, "DDGS_CACHE_ENABLED", True)):
            return None
        now = datetime.now(timezone.utc).timestamp()
        async with self._cache_lock:
            entry = self._cache.get(key)
            if not entry:
                return None
            if entry.expires_at <= now:
                self._cache.pop(key, None)
                return None
            self._cache.move_to_end(key)
            payload = dict(entry.payload)
            payload["cached_at"] = entry.cached_at
            payload["cache_ttl_seconds"] = ttl_seconds
            return payload

    async def _write_cache(self, key: str, payload: Dict[str, Any], ttl_seconds: int) -> None:
        if not bool(getattr(Config, "DDGS_CACHE_ENABLED", True)):
            return
        max_entries = max(1, int(getattr(Config, "DDGS_CACHE_MAX_ENTRIES", 200)))
        now = datetime.now(timezone.utc)
        expires_at = now.timestamp() + ttl_seconds
        cached_at = now.isoformat()
        async with self._cache_lock:
            self._cache[key] = _CacheEntry(payload=dict(payload), expires_at=expires_at, cached_at=cached_at)
            self._cache.move_to_end(key)
            while len(self._cache) > max_entries:
                self._cache.popitem(last=False)


_ddgs_search_mcp_service: DdgsSearchMcpService | None = None


def get_ddgs_search_mcp_service() -> DdgsSearchMcpService:
    global _ddgs_search_mcp_service
    if _ddgs_search_mcp_service is None:
        _ddgs_search_mcp_service = DdgsSearchMcpService()
    return _ddgs_search_mcp_service
