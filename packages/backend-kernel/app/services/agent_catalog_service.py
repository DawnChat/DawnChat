from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

import yaml

from app.agentv3.policy.agent_profile import list_builtin_profiles
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.utils.logger import get_logger

logger = get_logger("agent_catalog_service")

_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.DOTALL)
_JSON_LINE_COMMENT = re.compile(r"(?m)//.*$")
_JSON_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_JSON_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_jsonc(raw: str) -> str:
    text = _JSON_BLOCK_COMMENT.sub("", raw)
    text = _JSON_LINE_COMMENT.sub("", text)
    text = _JSON_TRAILING_COMMA.sub(r"\1", text)
    return text


def _load_json_or_jsonc(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists() or not path.is_file():
            return {}
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(_strip_jsonc(raw))
        return payload if isinstance(payload, dict) else {}
    except Exception as err:
        logger.warning("load config failed path=%s err=%s", str(path), err)
        return {}


def _parse_model(raw: Any) -> Optional[Dict[str, str]]:
    if isinstance(raw, dict):
        provider_id = str(raw.get("providerID") or raw.get("provider") or "").strip()
        model_id = str(raw.get("modelID") or raw.get("model") or "").strip()
        if provider_id and model_id:
            return {"providerID": provider_id, "modelID": model_id}
        return None
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if "/" not in value:
        return None
    provider_id, model_id = value.split("/", 1)
    provider_id = provider_id.strip()
    model_id = model_id.strip()
    if provider_id and model_id:
        return {"providerID": provider_id, "modelID": model_id}
    return None


def _load_frontmatter(md_path: Path) -> tuple[Dict[str, Any], str]:
    text = md_path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if not match:
        return {}, text.strip()
    frontmatter_str = match.group(1)
    body = match.group(2).strip()
    try:
        metadata = yaml.safe_load(frontmatter_str) or {}
        return metadata if isinstance(metadata, dict) else {}, body
    except Exception as err:
        logger.warning("load frontmatter failed path=%s err=%s", str(md_path), err)
        return {}, body


class AgentCatalogService:
    def _collect_config_dirs(self, workspace_path: Optional[str]) -> List[Path]:
        dirs: List[Path] = []
        if workspace_path:
            root = Path(workspace_path).expanduser()
            if root.exists() and root.is_dir():
                dirs.append(root / ".opencode")
                dirs.append(root)
        shared_dir = get_opencode_rules_service().get_current_dir()
        if shared_dir:
            dirs.append(Path(shared_dir).expanduser())
        return [item for item in dirs if item.exists() and item.is_dir()]

    def _load_open_config(self, workspace_path: Optional[str]) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for directory in self._collect_config_dirs(workspace_path):
            candidates = [
                directory / "opencode.jsonc",
                directory / "opencode.json",
            ]
            for candidate in candidates:
                payload = _load_json_or_jsonc(candidate)
                if not payload:
                    continue
                self._deep_merge(merged, payload)
        return merged

    def _load_markdown_agents(self, workspace_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
        rows: Dict[str, Dict[str, Any]] = {}
        shared_current = get_opencode_rules_service().get_current_dir()
        shared_current_path = Path(shared_current).resolve() if shared_current else None
        for directory in self._collect_config_dirs(workspace_path):
            for folder in ("agents", "agent"):
                target = directory / folder
                if not target.exists() or not target.is_dir():
                    continue
                for md_file in sorted(target.glob("*.md")):
                    metadata, content = _load_frontmatter(md_file)
                    agent_id = str(metadata.get("name") or md_file.stem).strip()
                    if not agent_id:
                        continue
                    rows[agent_id] = {
                        "id": agent_id,
                        "label": str(metadata.get("name") or agent_id),
                        "description": str(metadata.get("description") or "").strip(),
                        "mode": str(metadata.get("mode") or "primary"),
                        "hidden": bool(metadata.get("hidden")),
                        "source": (
                            "shared"
                            if shared_current_path is not None and directory.resolve() == shared_current_path
                            else "project"
                        ),
                        "permission": metadata.get("permission"),
                        "steps": metadata.get("steps") or metadata.get("maxSteps"),
                        "model": _parse_model(metadata.get("model")),
                        "prompt": content,
                    }
        return rows

    def list_agents(self, workspace_path: Optional[str] = None) -> List[Dict[str, Any]]:
        catalog: Dict[str, Dict[str, Any]] = {}
        for item in list_builtin_profiles():
            agent_id = str(item.get("id") or "").strip()
            if not agent_id:
                continue
            mode = "primary" if agent_id in {"build", "plan", "reviewer"} else "subagent"
            catalog[agent_id] = {
                "id": agent_id,
                "label": str(item.get("label") or agent_id),
                "description": str(item.get("description") or "").strip(),
                "mode": mode,
                "hidden": False,
                "source": "builtin",
                "permission": None,
                "steps": None,
                "model": None,
            }

        for agent_id, data in self._load_markdown_agents(workspace_path).items():
            catalog[agent_id] = {**catalog.get(agent_id, {}), **data}

        open_cfg = self._load_open_config(workspace_path)
        agent_cfg = open_cfg.get("agent")
        if isinstance(agent_cfg, dict):
            for agent_id, item in agent_cfg.items():
                if not isinstance(item, dict):
                    continue
                if bool(item.get("disable")):
                    catalog.pop(str(agent_id), None)
                    continue
                row = catalog.get(str(agent_id), {"id": str(agent_id), "source": "config"})
                row["id"] = str(agent_id)
                row["label"] = str(item.get("name") or row.get("label") or agent_id)
                if "description" in item:
                    row["description"] = str(item.get("description") or "")
                if "mode" in item:
                    row["mode"] = str(item.get("mode") or row.get("mode") or "primary")
                if "hidden" in item:
                    row["hidden"] = bool(item.get("hidden"))
                row["source"] = "config"
                if "permission" in item:
                    row["permission"] = item.get("permission")
                if "steps" in item or "maxSteps" in item:
                    row["steps"] = item.get("steps") if item.get("steps") is not None else item.get("maxSteps")
                if "model" in item:
                    row["model"] = _parse_model(item.get("model"))
                catalog[str(agent_id)] = row

        rows = list(catalog.values())
        rows.sort(key=lambda item: str(item.get("id") or ""))
        return rows

    def list_primary_visible_ids(self, workspace_path: Optional[str] = None) -> List[str]:
        result: List[str] = []
        for item in self.list_agents(workspace_path):
            mode = str(item.get("mode") or "primary").lower()
            hidden = bool(item.get("hidden"))
            if mode == "subagent" or hidden:
                continue
            result.append(str(item.get("id") or ""))
        return [item for item in result if item]

    def is_primary_visible(self, agent_id: str, workspace_path: Optional[str] = None) -> bool:
        target = str(agent_id or "").strip()
        if not target:
            return False
        return target in self.list_primary_visible_ids(workspace_path)

    def resolve_default_agent(self, workspace_path: Optional[str] = None) -> str:
        open_cfg = self._load_open_config(workspace_path)
        preferred = str(open_cfg.get("default_agent") or "").strip()
        if preferred and self.is_primary_visible(preferred, workspace_path):
            return preferred
        ids = self.list_primary_visible_ids(workspace_path)
        if "build" in ids:
            return "build"
        return ids[0] if ids else "build"

    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value


_agent_catalog_service: Optional[AgentCatalogService] = None


def get_agent_catalog_service() -> AgentCatalogService:
    global _agent_catalog_service
    if _agent_catalog_service is None:
        _agent_catalog_service = AgentCatalogService()
    return _agent_catalog_service

