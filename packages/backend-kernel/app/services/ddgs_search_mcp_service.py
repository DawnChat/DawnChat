from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.config import Config
from app.services.supabase_session_store import get_supabase_session_store
from app.services.unsplash_image_search_client import UnsplashImageSearchError, search_images_via_edge
from app.utils.logger import get_logger

try:
    from ddgs import DDGS
except Exception:  # pragma: no cover - runtime dependency fallback
    DDGS = None

logger = get_logger("ddgs_search_mcp_service")

_MVP_IMAGE_KEYWORD_RE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
_INVALID_IMAGE_QUERY_MESSAGE = (
    "query must be a single English keyword: lowercase letters, digits, hyphens; "
    "must start with a letter (max 64 characters)."
)
_IMAGE_TOOL_DESCRIPTION = (
    "Search images. When logged in, results may come from Unsplash—retain and display "
    "photographer attribution and links as required by Unsplash guidelines "
    "(https://unsplash.com/api-terms). "
    "MVP: `query` must be a single English keyword (see tool schema)."
)


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
                description=_IMAGE_TOOL_DESCRIPTION,
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

        raw_arguments: Dict[str, Any] = dict(arguments) if isinstance(arguments, dict) else {}

        if tool_name == "dawnchat.search.image":
            raw_q = str(raw_arguments.get("query") or "").strip()
            if not raw_q:
                return {"ok": False, "error_code": "invalid_arguments", "message": "query is required"}
            mvp_keyword = self._normalize_mvp_image_keyword(raw_q)
            if mvp_keyword is None:
                return {
                    "ok": False,
                    "error_code": "invalid_image_query",
                    "message": _INVALID_IMAGE_QUERY_MESSAGE,
                }
            raw_arguments = {**raw_arguments, "query": mvp_keyword}

        if DDGS is None and tool_name != "dawnchat.search.image":
            return {
                "ok": False,
                "error_code": "ddgs_unavailable",
                "message": "ddgs package is not available",
            }

        try:
            normalized = self._validate_arguments(tool_name, raw_arguments)
        except ValueError as err:
            return {"ok": False, "error_code": "invalid_arguments", "message": str(err)}

        if tool_name == "dawnchat.search.image":
            return await self._execute_image_search(normalized)

        ttl_seconds = self._resolve_ttl(tool_name)
        cache_key = self._build_cache_key(tool_name, normalized)
        cached_payload = await self._read_cache(cache_key, ttl_seconds)
        if cached_payload is not None:
            payload = dict(cached_payload)
            payload["cache_hit"] = True
            return {"ok": True, "data": payload}

        if DDGS is None:
            return {
                "ok": False,
                "error_code": "ddgs_unavailable",
                "message": "ddgs package is not available",
            }

        try:
            result_payload = await asyncio.to_thread(self._execute_ddgs_call, tool_name, normalized)
        except Exception as err:
            if self._is_no_results_error(err) and tool_name in {
                "dawnchat.search.text",
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

    @staticmethod
    def _normalize_mvp_image_keyword(raw: str) -> Optional[str]:
        normalized = str(raw or "").strip().lower()
        if not normalized:
            return None
        if _MVP_IMAGE_KEYWORD_RE.fullmatch(normalized):
            return normalized
        return None

    async def _execute_image_search(self, normalized: Dict[str, Any]) -> Dict[str, Any]:
        ttl_seconds = self._resolve_ttl("dawnchat.search.image")
        token = await get_supabase_session_store().get_usable_access_token()

        if token:
            cache_args_u = {**normalized, "_cache_provider": "unsplash"}
            cache_key_u = self._build_cache_key("dawnchat.search.image", cache_args_u)
            cached_u = await self._read_cache(cache_key_u, ttl_seconds)
            if cached_u is not None:
                payload_u = dict(cached_u)
                payload_u["cache_hit"] = True
                return {"ok": True, "data": payload_u}
            try:
                edge = await search_images_via_edge(
                    access_token=token,
                    keyword=str(normalized["query"]),
                    max_results=int(normalized["max_results"]),
                )
            except UnsplashImageSearchError as err:
                logger.info(
                    "image search unsplash path skipped code=%s msg=%s",
                    err.code,
                    err,
                )
            else:
                edge_items = edge.get("items")
                items_raw: List[Any] = edge_items if isinstance(edge_items, list) else []
                items = [self._merge_unsplash_image_item(row) for row in items_raw if isinstance(row, dict)]
                result_payload: Dict[str, Any] = {
                    "tool": "dawnchat.search.image",
                    "query": normalized["query"],
                    "region": normalized["region"],
                    "requested_region": normalized["region"],
                    "safesearch": normalized["safesearch"],
                    "requested_safesearch": normalized["safesearch"],
                    "max_results": normalized["max_results"],
                    "items": items,
                    "provider": "unsplash",
                    "edge_cache_hit": bool(edge.get("cache_hit")),
                    "fallback_used": False,
                }
                result_payload["cache_hit"] = False
                await self._write_cache(cache_key_u, result_payload, ttl_seconds)
                return {"ok": True, "data": result_payload}

        if DDGS is None:
            return {
                "ok": False,
                "error_code": "ddgs_unavailable",
                "message": "ddgs package is not available",
            }

        cache_args_d = {**normalized, "_cache_provider": "ddgs"}
        cache_key_d = self._build_cache_key("dawnchat.search.image", cache_args_d)
        cached_d = await self._read_cache(cache_key_d, ttl_seconds)
        if cached_d is not None:
            payload_d = dict(cached_d)
            payload_d["cache_hit"] = True
            return {"ok": True, "data": payload_d}

        try:
            result_payload = await asyncio.to_thread(self._execute_ddgs_call, "dawnchat.search.image", normalized)
        except Exception as err:
            if self._is_no_results_error(err):
                logger.info("ddgs image search no results query=%s", normalized.get("query"))
                empty = self._build_empty_search_payload(
                    tool_name="dawnchat.search.image",
                    arguments=normalized,
                )
                empty["provider"] = "ddgs"
                return {"ok": True, "data": empty}
            logger.warning("ddgs image search failed error=%s", err)
            return {"ok": False, "error_code": "ddgs_request_failed", "message": str(err)}

        result_payload["provider"] = "ddgs"
        result_payload["cache_hit"] = False
        await self._write_cache(cache_key_d, result_payload, ttl_seconds)
        return {"ok": True, "data": result_payload}

    def _merge_unsplash_image_item(self, row: Dict[str, Any]) -> Dict[str, Any]:
        normalized_rows = self._normalize_image_items([row])
        item: Dict[str, Any] = (
            dict(normalized_rows[0])
            if normalized_rows
            else {"title": "", "url": "", "thumbnail": "", "source": ""}
        )
        for key in ("links", "user", "unsplash_id"):
            if key in row:
                item[key] = row[key]
        return item

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
