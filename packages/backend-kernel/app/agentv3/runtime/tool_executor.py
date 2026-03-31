from __future__ import annotations

from fnmatch import fnmatch
import json
from typing import Any, Dict, List, Optional

from app.agentv3.policy.permission_engine import PermissionEngine
from app.config import Config


class RuntimeToolExecutor:
    def __init__(self, permission_engine: PermissionEngine):
        self._permission_engine = permission_engine

    def parse_arguments(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def tool_result_text(self, result: Dict[str, Any], tool_name: str = "") -> str:
        if result.get("ok"):
            payload = result.get("data")
            if tool_name == "read" and isinstance(payload, dict):
                core = payload.get("content")
                if isinstance(core, str):
                    return core
            if isinstance(payload, str):
                return payload
            return json.dumps(payload, ensure_ascii=False)
        return f"error: {self.tool_error_text(result)}"

    def tool_error_text(self, result: Dict[str, Any]) -> str:
        error_text = str(result.get("error") or "").strip()
        if error_text:
            return error_text
        data = result.get("data")
        if isinstance(data, dict):
            exit_code = data.get("exit_code")
            stderr = str(data.get("stderr") or "").strip()
            if exit_code is not None and stderr:
                return f"exit_code={exit_code}: {stderr[:300]}"
            if exit_code is not None:
                return f"exit_code={exit_code}"
        return "tool_error"

    def tool_failure_signature(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        try:
            normalized_args = json.dumps(tool_args or {}, sort_keys=True, ensure_ascii=False)
        except Exception:
            normalized_args = "{}"
        return f"{tool_name}:{normalized_args}"

    def decide_tool_failure_policy(self, result: Dict[str, Any], retry_count: int) -> str:
        if bool(result.get("ok")):
            return "continue_with_feedback"
        retryable = bool(result.get("retryable"))
        retry_enabled = bool(getattr(Config, "AGENTV3_ENABLE_STEP_RETRY_ON_RETRYABLE", True))
        retry_limit = max(0, int(getattr(Config, "AGENTV3_STEP_RETRY_LIMIT", 1)))
        if retry_enabled and retryable and retry_count < retry_limit:
            return "retry_step"
        code = str(result.get("error_code") or "").strip().lower()
        if code in {"path_outside_workspace", "tool_not_found", "tool_no_executor"}:
            return "stop_error"
        return "continue_with_feedback"

    def decide_permission(
        self,
        permission: str,
        target: str,
        permission_rules: Optional[List[Dict[str, str]]],
        permission_default_action: str = "ask",
    ) -> str:
        if permission_rules:
            for rule in permission_rules:
                if not isinstance(rule, dict):
                    continue
                rule_permission = str(rule.get("permission") or "").strip() or "*"
                rule_pattern = str(rule.get("pattern") or "").strip() or "*"
                if not self.wildcard_match(permission, rule_permission):
                    continue
                if not self.wildcard_match(target, rule_pattern):
                    continue
                action = str(rule.get("action") or "").strip().lower()
                if action in {"allow", "deny", "ask"}:
                    return action
        self._permission_engine.set_default_action(permission_default_action)
        return self._permission_engine.decide(permission, target)

    def wildcard_match(self, value: str, pattern: str) -> bool:
        return fnmatch(value, pattern)
