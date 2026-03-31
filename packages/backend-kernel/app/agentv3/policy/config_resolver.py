from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.agentv3.policy.agent_profile import get_profile_rules
from app.config import Config
from app.services.agent_catalog_service import get_agent_catalog_service
from app.utils.logger import get_logger

logger = get_logger("agentv3_config_resolver")

_JSON_LINE_COMMENT = re.compile(r"(?m)//.*$")
_JSON_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_JSON_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _strip_jsonc(raw: str) -> str:
    text = _JSON_BLOCK_COMMENT.sub("", raw)
    text = _JSON_LINE_COMMENT.sub("", text)
    return _JSON_TRAILING_COMMA.sub(r"\1", text)


class AgentV3ConfigResolver:
    def __init__(self):
        self._global_config_path = Path(str(Config.AGENTV3_GLOBAL_CONFIG_PATH)).expanduser()
        self._project_config_relative_path = str(Config.AGENTV3_PROJECT_CONFIG_RELATIVE_PATH or ".dawnchat/agentv3.json")

    def resolve(
        self,
        *,
        session_row: Dict[str, Any],
        workspace_path: str,
        default_model: Optional[Dict[str, str]],
        shared_config_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        global_open_cfg = self._load_json(self._global_config_path)
        project_open_cfg = self._load_project_open_config(workspace_path)
        shared_open_cfg = self._load_shared_open_config(shared_config_dir)
        session_open_cfg: Dict[str, Any] = {}
        raw_session_open_cfg = session_row.get("opencode_config")
        if isinstance(raw_session_open_cfg, dict):
            session_open_cfg = raw_session_open_cfg
        legacy_project_cfg = self._load_legacy_project_config(workspace_path)
        session_cfg: Dict[str, Any] = {}
        raw_session_cfg = session_row.get("config")
        if isinstance(raw_session_cfg, dict):
            session_cfg = raw_session_cfg

        open_cfg: Dict[str, Any] = {}
        self._deep_merge(open_cfg, global_open_cfg)
        self._deep_merge(open_cfg, project_open_cfg)
        self._deep_merge(open_cfg, shared_open_cfg)
        self._deep_merge(open_cfg, session_open_cfg)

        default_agent = str(open_cfg.get("default_agent") or "").strip()
        if not default_agent:
            default_agent = get_agent_catalog_service().resolve_default_agent(workspace_path)
        if not get_agent_catalog_service().is_primary_visible(default_agent, workspace_path):
            default_agent = get_agent_catalog_service().resolve_default_agent(workspace_path)

        selected_agent = str(session_cfg.get("agent") or default_agent or "build").strip() or "build"
        if not get_agent_catalog_service().is_primary_visible(selected_agent, workspace_path):
            selected_agent = default_agent or "build"

        merged: Dict[str, Any] = {
            "agent": selected_agent,
            "model": default_model,
            "thinking": {"enabled": True, "effort": "medium", "budget_tokens": 0},
            "max_steps": int(Config.AGENTV3_MAX_STEPS),
            "permission_rules": [],
            "permission_default_action": str(Config.AGENTV3_PERMISSION_DEFAULT_ACTION or "ask").lower(),
            "system_instructions": self._load_system_instructions(
                open_cfg=open_cfg,
                workspace_path=workspace_path,
                shared_config_dir=shared_config_dir,
            ),
            "_source": {
                "agent": "opencode",
                "model": "opencode",
                "thinking": "session",
                "max_steps": "opencode",
                "permission_rules": "opencode",
                "permission_default_action": "opencode",
            },
        }
        self._merge_open_config(merged, open_cfg, source_name="opencode")
        self._merge_legacy_layer(merged, legacy_project_cfg, "legacy_project")
        self._merge_legacy_layer(merged, session_cfg, "session")

        profile = str(merged.get("agent") or "build")
        base_rules = get_profile_rules(profile)
        custom_rules = merged.get("permission_rules")
        if isinstance(custom_rules, list):
            base_rules.extend([dict(item) for item in custom_rules if isinstance(item, dict)])
        merged["permission_rules"] = self._normalize_rules(base_rules)
        action = str(merged.get("permission_default_action") or "ask").lower()
        if action not in {"allow", "deny", "ask"}:
            action = "ask"
        merged["permission_default_action"] = action
        return merged

    def _load_project_open_config(self, workspace_path: str) -> Dict[str, Any]:
        root = Path(str(workspace_path or "")).expanduser()
        if not root.exists():
            return {}
        merged: Dict[str, Any] = {}
        for candidate in (
            root / "opencode.jsonc",
            root / "opencode.json",
            root / ".opencode" / "opencode.jsonc",
            root / ".opencode" / "opencode.json",
        ):
            self._deep_merge(merged, self._load_json(candidate))
        return merged

    def _load_legacy_project_config(self, workspace_path: str) -> Dict[str, Any]:
        root = Path(str(workspace_path or "")).expanduser()
        if not root.exists():
            return {}
        return self._load_json(root / self._project_config_relative_path)

    def _load_shared_open_config(self, shared_config_dir: Optional[str]) -> Dict[str, Any]:
        shared = str(shared_config_dir or "").strip()
        if not shared:
            return {}
        root = Path(shared).expanduser()
        if not root.exists() or not root.is_dir():
            return {}
        merged: Dict[str, Any] = {}
        for candidate in (root / "opencode.jsonc", root / "opencode.json"):
            self._deep_merge(merged, self._load_json(candidate))
        return merged

    def _load_json(self, path: Path) -> Dict[str, Any]:
        try:
            if not path.exists():
                return {}
            payload = json.loads(_strip_jsonc(path.read_text(encoding="utf-8")))
            if isinstance(payload, dict):
                return payload
        except Exception as err:
            logger.warning("load config failed path=%s err=%s", str(path), err)
        return {}

    def _merge_open_config(self, merged: Dict[str, Any], layer: Dict[str, Any], source_name: str) -> None:
        if not isinstance(layer, dict):
            return
        source = merged.setdefault("_source", {})
        if isinstance(layer.get("default_agent"), str) and layer.get("default_agent"):
            merged["agent"] = str(layer.get("default_agent")).strip()
            source["agent"] = source_name
        normalized_model = self._normalize_model(layer.get("model"))
        if normalized_model is not None:
            merged["model"] = normalized_model
            source["model"] = source_name
        selected_agent = str(merged.get("agent") or "build").strip() or "build"
        agent_cfg = layer.get("agent") if isinstance(layer.get("agent"), dict) else {}
        selected_agent_cfg = agent_cfg.get(selected_agent) if isinstance(agent_cfg, dict) else {}
        max_steps = self._safe_int(
            (
                selected_agent_cfg.get("steps")
                if isinstance(selected_agent_cfg, dict) and selected_agent_cfg.get("steps") is not None
                else (
                    selected_agent_cfg.get("maxSteps") if isinstance(selected_agent_cfg, dict) else layer.get("max_steps")
                )
            ),
            default=0,
        )
        if max_steps > 0:
            merged["max_steps"] = max_steps
            source["max_steps"] = source_name
        permission_rules = self._permission_to_rules(layer.get("permission"))
        if isinstance(selected_agent_cfg, dict):
            permission_rules.extend(self._permission_to_rules(selected_agent_cfg.get("permission")))
        if permission_rules:
            merged["permission_rules"] = permission_rules
            source["permission_rules"] = source_name
        default_action = str(layer.get("permission_default_action") or "").strip().lower()
        if not default_action:
            default_action = self._infer_default_action(layer.get("permission"))
        if default_action in {"allow", "deny", "ask"}:
            merged["permission_default_action"] = default_action
            source["permission_default_action"] = source_name

    def _merge_legacy_layer(self, merged: Dict[str, Any], layer: Dict[str, Any], source_name: str) -> None:
        if not isinstance(layer, dict):
            return
        source = merged.setdefault("_source", {})
        if isinstance(layer.get("agent"), str) and layer.get("agent"):
            merged["agent"] = str(layer.get("agent")).strip()
            source["agent"] = source_name
        normalized_model = self._normalize_model(layer.get("model"))
        if normalized_model is not None:
            merged["model"] = normalized_model
            source["model"] = source_name
        thinking = layer.get("thinking")
        if isinstance(thinking, dict):
            merged["thinking"] = {
                "enabled": bool(thinking.get("enabled")),
                "effort": str(thinking.get("effort") or "medium"),
                "budget_tokens": self._safe_int(thinking.get("budget_tokens"), default=0),
            }
            source["thinking"] = source_name
        max_steps = self._safe_int(layer.get("max_steps"), default=0)
        if max_steps > 0:
            merged["max_steps"] = max_steps
            source["max_steps"] = source_name
        rules = layer.get("permission_rules")
        if isinstance(rules, list):
            merged["permission_rules"] = [dict(item) for item in rules if isinstance(item, dict)]
            source["permission_rules"] = source_name
        default_action = str(layer.get("permission_default_action") or "").strip().lower()
        if default_action in {"allow", "deny", "ask"}:
            merged["permission_default_action"] = default_action
            source["permission_default_action"] = source_name

    def _normalize_model(self, value: Any) -> Optional[Dict[str, str]]:
        if isinstance(value, dict):
            provider_id = str(value.get("providerID") or value.get("provider") or "").strip()
            model_id = str(value.get("modelID") or value.get("model") or "").strip()
            if provider_id and model_id:
                return {"providerID": provider_id, "modelID": model_id}
        if isinstance(value, str):
            raw = value.strip()
            if "/" in raw:
                provider_id, model_id = raw.split("/", 1)
                provider_id = provider_id.strip()
                model_id = model_id.strip()
                if provider_id and model_id:
                    return {"providerID": provider_id, "modelID": model_id}
            if ":" in raw:
                provider_id, model_id = raw.split(":", 1)
                provider_id = provider_id.strip()
                model_id = model_id.strip()
                if provider_id and model_id:
                    return {"providerID": provider_id, "modelID": model_id}
        return None

    def _normalize_rules(self, rows: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        for row in rows:
            permission = str(row.get("permission") or "").strip()
            pattern = str(row.get("pattern") or "").strip() or "*"
            action = str(row.get("action") or "").strip().lower()
            if not permission or action not in {"allow", "deny", "ask"}:
                continue
            result.append({"permission": permission, "pattern": pattern, "action": action})
        return result

    def _safe_int(self, value: Any, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed

    def _permission_to_rules(self, raw: Any) -> List[Dict[str, str]]:
        result: List[Dict[str, str]] = []
        if isinstance(raw, str):
            action = str(raw).strip().lower()
            if action in {"allow", "deny", "ask"}:
                result.append({"permission": "*", "pattern": "*", "action": action})
            return result
        if not isinstance(raw, dict):
            return result
        for permission, value in raw.items():
            permission_key = str(permission or "").strip()
            if not permission_key:
                continue
            if isinstance(value, str):
                action = value.strip().lower()
                if action in {"allow", "deny", "ask"}:
                    result.append({"permission": permission_key, "pattern": "*", "action": action})
                continue
            if not isinstance(value, dict):
                continue
            for pattern, action_raw in value.items():
                action = str(action_raw or "").strip().lower()
                if action not in {"allow", "deny", "ask"}:
                    continue
                result.append(
                    {
                        "permission": permission_key,
                        "pattern": str(pattern or "*").strip() or "*",
                        "action": action,
                    }
                )
        return result

    def _infer_default_action(self, permission_cfg: Any) -> str:
        if isinstance(permission_cfg, str):
            action = str(permission_cfg).strip().lower()
            return action if action in {"allow", "deny", "ask"} else "ask"
        if not isinstance(permission_cfg, dict):
            return "ask"
        wildcard = permission_cfg.get("*")
        if isinstance(wildcard, str):
            action = wildcard.strip().lower()
            if action in {"allow", "deny", "ask"}:
                return action
        return "ask"

    def _read_text(self, path: Path) -> Optional[str]:
        try:
            if not path.exists() or not path.is_file():
                return None
            content = path.read_text(encoding="utf-8").strip()
            if not content:
                return None
            return f"Instructions from: {path}\\n{content}"
        except Exception:
            return None

    def _load_system_instructions(
        self,
        *,
        open_cfg: Dict[str, Any],
        workspace_path: str,
        shared_config_dir: Optional[str],
    ) -> List[str]:
        results: List[str] = []
        visited: set[str] = set()
        workspace = Path(str(workspace_path or "")).expanduser()
        shared = Path(str(shared_config_dir).strip()).expanduser() if str(shared_config_dir or "").strip() else None
        instructions = open_cfg.get("instructions")
        if isinstance(instructions, list):
            for item in instructions:
                if not isinstance(item, str):
                    continue
                raw = item.strip()
                if not raw or raw.startswith("http://") or raw.startswith("https://"):
                    continue
                candidates: List[Path] = []
                target = Path(raw).expanduser()
                if target.is_absolute():
                    candidates.append(target)
                if workspace.exists():
                    candidates.append((workspace / raw).resolve())
                if shared and shared.exists():
                    candidates.append((shared / raw).resolve())
                for candidate in candidates:
                    key = str(candidate)
                    if key in visited:
                        continue
                    text = self._read_text(candidate)
                    if text:
                        results.append(text)
                        visited.add(key)
        for base in (
            workspace / ".opencode" / "context" if workspace.exists() else None,
            shared / "context" if shared else None,
        ):
            if not base or not base.exists() or not base.is_dir():
                continue
            for file_path in sorted(base.glob("*.md")):
                key = str(file_path.resolve())
                if key in visited:
                    continue
                text = self._read_text(file_path)
                if text:
                    results.append(text)
                    visited.add(key)
        return results

    def _deep_merge(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value
