from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any, Dict, List, Literal

PermissionDecision = Literal["once", "always", "reject"]
PermissionAction = Literal["allow", "deny", "ask"]


@dataclass(slots=True)
class PermissionRule:
    permission: str
    pattern: str
    action: PermissionAction


class PermissionEngine:
    def __init__(self, rules: List[PermissionRule] | None = None, default_action: PermissionAction = "ask"):
        self._rules = rules or []
        self._default_action: PermissionAction = default_action if default_action in {"allow", "deny", "ask"} else "ask"

    def decide(self, permission: str, target: str) -> PermissionAction:
        for rule in reversed(self._rules):
            if not fnmatch(permission, rule.permission):
                continue
            if fnmatch(target, rule.pattern):
                return rule.action
        return self._default_action

    def set_rules(self, rules: List[PermissionRule]) -> None:
        self._rules = list(rules)

    def set_default_action(self, action: str) -> None:
        normalized = str(action or "").strip().lower()
        if normalized in {"allow", "deny", "ask"}:
            self._default_action = normalized  # type: ignore[assignment]

    def export_rules(self) -> List[Dict[str, Any]]:
        return [
            {"permission": rule.permission, "pattern": rule.pattern, "action": rule.action}
            for rule in self._rules
        ]

