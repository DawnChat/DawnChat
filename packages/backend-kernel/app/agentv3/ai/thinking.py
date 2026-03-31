from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

SUPPORTED_EFFORTS = {"low", "medium", "high", "max"}


@dataclass(slots=True)
class ThinkingConfig:
    enabled: bool
    effort: str = "medium"
    budget_tokens: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "effort": self.effort,
            "budget_tokens": self.budget_tokens,
        }


def normalize_effort(value: Any, default: str = "medium") -> str:
    effort = str(value or default).strip().lower()
    if effort not in SUPPORTED_EFFORTS:
        return default
    return effort


def normalize_budget_tokens(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0, int(value))
    return default


def infer_auto_thinking(model_key: str) -> ThinkingConfig:
    raw = str(model_key or "").strip().lower()
    if not raw:
        return ThinkingConfig(enabled=False, effort="medium", budget_tokens=0)
    if ":" in raw:
        provider, model_id = raw.split(":", 1)
    else:
        provider, model_id = "unknown", raw
    if provider in {"gemini", "google", "vertex_ai", "vertexai"} or "gemini" in model_id:
        return ThinkingConfig(enabled=True, effort="high", budget_tokens=16000)
    if provider in {"anthropic", "claude"} or "claude" in model_id:
        return ThinkingConfig(enabled=True, effort="high", budget_tokens=8000)
    if any(token in model_id for token in {"o1", "o3", "gpt-5", "reasoning"}):
        return ThinkingConfig(enabled=True, effort="medium", budget_tokens=0)
    return ThinkingConfig(enabled=False, effort="medium", budget_tokens=0)


def merge_thinking(
    model_key: str,
    override: Optional[Dict[str, Any]],
) -> ThinkingConfig:
    auto = infer_auto_thinking(model_key)
    if not isinstance(override, dict):
        return auto
    enabled = bool(override.get("enabled", auto.enabled))
    effort = normalize_effort(override.get("effort"), default=auto.effort)
    budget = normalize_budget_tokens(override.get("budget_tokens"), default=auto.budget_tokens)
    return ThinkingConfig(enabled=enabled, effort=effort, budget_tokens=budget)


def build_provider_thinking_options(
    *,
    provider: str,
    model_name: str,
    enabled: bool,
    effort: Optional[str],
    budget_tokens: Optional[int],
) -> Dict[str, Any]:
    normalized_provider = str(provider or "").strip().lower()
    normalized_model = str(model_name or "").strip().lower()
    normalized_effort = normalize_effort(effort, default="medium")
    normalized_budget = normalize_budget_tokens(budget_tokens, default=0)
    if not enabled:
        return {"enabled": False}

    result: Dict[str, Any] = {"enabled": True}
    if normalized_effort:
        result["reasoning_effort"] = normalized_effort

    if normalized_provider in {"gemini", "google", "vertex_ai", "vertexai"} or "gemini" in normalized_model:
        thinking_config: Dict[str, Any] = {"includeThoughts": True}
        if normalized_budget > 0:
            thinking_config["thinkingBudget"] = normalized_budget
        else:
            thinking_config["thinkingLevel"] = normalized_effort if normalized_effort in {"low", "high"} else "high"
        result["thinking_config"] = thinking_config
        return result

    if normalized_provider in {"anthropic", "claude"} or "claude" in normalized_model:
        thinking_payload: Dict[str, Any] = {"type": "enabled"}
        if normalized_budget > 0:
            thinking_payload["budget_tokens"] = normalized_budget
        result["thinking"] = thinking_payload
        return result

    result["reasoning_summary"] = "auto"
    return result
