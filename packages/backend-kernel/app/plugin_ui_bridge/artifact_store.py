from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.plugins import get_plugin_manager

from .errors import PluginUIBridgeError
from .models import BridgeOperation


@dataclass(slots=True)
class ArtifactWriteResult:
    data: Dict[str, Any]
    artifacts: List[Dict[str, Any]]


class UiArtifactStore:
    def resolve_plugin_root(self, plugin_id: str) -> Path:
        manager = get_plugin_manager()
        plugin = manager.get_plugin(plugin_id)
        if not plugin:
            raise PluginUIBridgeError(code="plugin_not_found", message=f"plugin not found: {plugin_id}")
        plugin_path = str(getattr(plugin.manifest, "plugin_path", "") or "").strip()
        if not plugin_path:
            raise PluginUIBridgeError(code="plugin_path_missing", message=f"plugin path missing: {plugin_id}")
        root = Path(plugin_path).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise PluginUIBridgeError(code="plugin_path_invalid", message=f"invalid plugin path: {root}")
        return root

    def write_result(
        self,
        plugin_id: str,
        request_id: str,
        op: BridgeOperation,
        result: Dict[str, Any],
    ) -> ArtifactWriteResult:
        root = self.resolve_plugin_root(plugin_id)
        day = datetime.now().strftime("%Y%m%d")
        out_dir = root / ".debug" / "ui-artifacts" / day / request_id
        out_dir.mkdir(parents=True, exist_ok=True)

        artifacts: List[Dict[str, Any]] = []
        main_file = self._main_filename(op)
        main_bytes = self._write_json(out_dir / main_file, result)
        artifacts.append(self._to_artifact_meta("json", out_dir / main_file, main_bytes))

        normalized = self._strip_binary_fields(result)
        screenshot_meta = self._extract_screenshot(result)
        if screenshot_meta:
            mime, b64_value = screenshot_meta
            image_path, image_size = self._write_screenshot(out_dir, b64_value, mime)
            artifacts.append(self._to_artifact_meta("image", image_path, image_size, mime=mime))

        normalized["artifact_dir"] = str(out_dir.resolve())
        return ArtifactWriteResult(data=normalized, artifacts=artifacts)

    @staticmethod
    def _main_filename(op: BridgeOperation) -> str:
        if op == BridgeOperation.DESCRIBE:
            return "dom_snapshot.json"
        if op == BridgeOperation.QUERY:
            return "query_result.json"
        if op == BridgeOperation.SCROLL:
            return "scroll_result.json"
        return "action_result.json"

    @staticmethod
    def _write_json(path: Path, payload: Dict[str, Any]) -> int:
        text = json.dumps(payload, ensure_ascii=False, indent=2)
        data = text.encode("utf-8")
        path.write_bytes(data)
        return len(data)

    @staticmethod
    def _strip_binary_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
        cloned = json.loads(json.dumps(payload, ensure_ascii=False))
        data = cloned.get("data")
        if isinstance(data, dict):
            screenshot = data.get("screenshot")
            if isinstance(screenshot, dict):
                screenshot.pop("base64", None)
            data.pop("screenshot_base64", None)
        return cloned

    @staticmethod
    def _extract_screenshot(payload: Dict[str, Any]) -> Tuple[str, str] | None:
        data = payload.get("data")
        if not isinstance(data, dict):
            return None
        screenshot = data.get("screenshot")
        if isinstance(screenshot, dict):
            b64 = str(screenshot.get("base64") or "").strip()
            if b64:
                mime = str(screenshot.get("mime") or "image/png").strip() or "image/png"
                return mime, b64
        direct = str(data.get("screenshot_base64") or "").strip()
        if direct:
            return "image/png", direct
        return None

    @staticmethod
    def _write_screenshot(out_dir: Path, base64_text: str, mime: str) -> Tuple[Path, int]:
        ext = "png" if mime.lower() == "image/png" else "jpg"
        image_path = out_dir / f"viewport.{ext}"
        decoded = base64.b64decode(base64_text, validate=True)
        image_path.write_bytes(decoded)
        return image_path, len(decoded)

    @staticmethod
    def _to_artifact_meta(kind: str, path: Path, size_bytes: int, mime: str = "") -> Dict[str, Any]:
        binary = path.read_bytes()
        payload: Dict[str, Any] = {
            "kind": kind,
            "path": str(path.resolve()),
            "bytes": size_bytes,
            "sha256": hashlib.sha256(binary).hexdigest(),
        }
        if mime:
            payload["mime"] = mime
        return payload
