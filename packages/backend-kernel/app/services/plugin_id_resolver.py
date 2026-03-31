from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal

from app.plugins import get_plugin_manager

ResolveSource = Literal["exact", "path_basename", "safe_name"]


@dataclass(slots=True)
class PluginIdResolveError(Exception):
    code: str
    message: str
    details: Dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ResolvedPluginId:
    canonical_plugin_id: str
    raw_plugin_id: str
    resolve_source: ResolveSource


class PluginIdResolver:
    def resolve(self, raw_plugin_id: str) -> ResolvedPluginId:
        raw_key = str(raw_plugin_id or "").strip()
        if not raw_key:
            raise PluginIdResolveError(code="plugin_not_found", message="plugin not found: ")
        manager = get_plugin_manager()

        if manager.get_plugin_snapshot(raw_key) is not None:
            return ResolvedPluginId(
                canonical_plugin_id=raw_key,
                raw_plugin_id=raw_key,
                resolve_source="exact",
            )

        basename_key = self._extract_basename(raw_key)
        if basename_key and basename_key != raw_key and manager.get_plugin_snapshot(basename_key) is not None:
            return ResolvedPluginId(
                canonical_plugin_id=basename_key,
                raw_plugin_id=raw_key,
                resolve_source="path_basename",
            )

        safe_candidates = self._match_safe_name_candidates(raw_key=raw_key, basename_key=basename_key)
        if len(safe_candidates) == 1:
            return ResolvedPluginId(
                canonical_plugin_id=safe_candidates[0],
                raw_plugin_id=raw_key,
                resolve_source="safe_name",
            )
        if len(safe_candidates) > 1:
            raise PluginIdResolveError(
                code="ambiguous_plugin_id",
                message=f"plugin id is ambiguous: {raw_key}",
                details={"candidates": safe_candidates},
            )
        raise PluginIdResolveError(code="plugin_not_found", message=f"plugin not found: {raw_key}")

    def _match_safe_name_candidates(self, *, raw_key: str, basename_key: str) -> list[str]:
        keys = {self._safe_name(raw_key)}
        if basename_key:
            keys.add(self._safe_name(basename_key))
        manager = get_plugin_manager()
        matched: set[str] = set()
        for plugin in manager.list_plugins() or []:
            plugin_id = str((plugin or {}).get("id") or "").strip()
            if not plugin_id:
                continue
            if self._safe_name(plugin_id) in keys:
                matched.add(plugin_id)
        return sorted(matched)

    @staticmethod
    def _extract_basename(value: str) -> str:
        cleaned = str(value or "").strip().rstrip("/\\")
        if not cleaned:
            return ""
        return cleaned.replace("\\", "/").split("/")[-1].strip()

    @staticmethod
    def _safe_name(plugin_id: str) -> str:
        return str(plugin_id or "").replace("/", "_").replace(".", "_")


_plugin_id_resolver: PluginIdResolver | None = None


def get_plugin_id_resolver() -> PluginIdResolver:
    global _plugin_id_resolver
    if _plugin_id_resolver is None:
        _plugin_id_resolver = PluginIdResolver()
    return _plugin_id_resolver
