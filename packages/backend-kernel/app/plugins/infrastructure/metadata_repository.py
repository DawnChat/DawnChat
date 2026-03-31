from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.utils.logger import get_logger

logger = get_logger("plugin_metadata_repository")


class PluginMetadataRepository:
    def __init__(self, metadata_file: Path) -> None:
        self._metadata_file = metadata_file
        self._metadata = self._load()

    def all(self) -> dict[str, dict[str, Any]]:
        return self._metadata

    def upsert(self, plugin_id: str, patch: dict[str, Any]) -> None:
        current = self._metadata.get(plugin_id, {})
        current.update(patch)
        self._metadata[plugin_id] = current
        self._save()

    def remove(self, plugin_id: str) -> None:
        if plugin_id not in self._metadata:
            return
        self._metadata.pop(plugin_id, None)
        self._save()

    def update_publish(self, plugin_id: str, patch: dict[str, Any]) -> None:
        self._update_nested(plugin_id, "web_publish", patch)

    def get_publish(self, plugin_id: str) -> dict[str, Any]:
        return dict((self._metadata.get(plugin_id) or {}).get("web_publish") or {})

    def update_mobile_publish(self, plugin_id: str, patch: dict[str, Any]) -> None:
        self._update_nested(plugin_id, "mobile_publish", patch)

    def get_mobile_publish(self, plugin_id: str) -> dict[str, Any]:
        return dict((self._metadata.get(plugin_id) or {}).get("mobile_publish") or {})

    def _update_nested(self, plugin_id: str, key: str, patch: dict[str, Any]) -> None:
        current = dict(self._metadata.get(plugin_id, {}))
        target = dict(current.get(key) or {})
        target.update(patch)
        current[key] = target
        self._metadata[plugin_id] = current
        self._save()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self._metadata_file.exists():
            return {}
        try:
            data = json.loads(self._metadata_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        except Exception as e:
            logger.warning("Failed to load plugin metadata: %s", e)
        return {}

    def _save(self) -> None:
        try:
            self._metadata_file.parent.mkdir(parents=True, exist_ok=True)
            self._metadata_file.write_text(
                json.dumps(self._metadata, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning("Failed to save plugin metadata: %s", e)
