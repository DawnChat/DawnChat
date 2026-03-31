from __future__ import annotations

from typing import Dict, List

BUILTIN_AGENT_PROFILES: List[Dict[str, str]] = [
    {"id": "build", "label": "build", "description": "default coding profile"},
    {"id": "plan", "label": "plan", "description": "read-first analysis profile"},
    {"id": "general", "label": "general", "description": "general task profile"},
    {"id": "explore", "label": "explore", "description": "exploration profile"},
]

BUILTIN_PERMISSION_RULES: Dict[str, List[Dict[str, str]]] = {
    "build": [
        {"permission": "*", "pattern": "*", "action": "allow"},
    ],
    "plan": [
        {"permission": "bash", "pattern": "*", "action": "deny"},
        {"permission": "write", "pattern": "*", "action": "deny"},
        {"permission": "read", "pattern": "*", "action": "allow"},
        {"permission": "search", "pattern": "*", "action": "allow"},
        {"permission": "glob", "pattern": "*", "action": "allow"},
    ],
    "general": [
        {"permission": "*", "pattern": "*", "action": "allow"},
    ],
    "explore": [
        {"permission": "write", "pattern": "*", "action": "deny"},
        {"permission": "bash", "pattern": "*", "action": "ask"},
        {"permission": "read", "pattern": "*", "action": "allow"},
        {"permission": "search", "pattern": "*", "action": "allow"},
        {"permission": "glob", "pattern": "*", "action": "allow"},
    ],
}


def list_builtin_profiles() -> List[Dict[str, str]]:
    return [dict(item) for item in BUILTIN_AGENT_PROFILES]


def get_profile_rules(profile_id: str) -> List[Dict[str, str]]:
    key = str(profile_id or "build").strip() or "build"
    rows = BUILTIN_PERMISSION_RULES.get(key) or BUILTIN_PERMISSION_RULES["build"]
    return [dict(item) for item in rows]
