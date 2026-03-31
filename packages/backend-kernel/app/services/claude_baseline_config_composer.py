from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.services.model_list_service import SUPPORTED_PROVIDERS
from app.services.opencode_instruction_resolver import OpenCodeInstructionResolver
from app.storage import storage_manager


@dataclass
class ClaudeBaselineComposeResult:
    config: Dict[str, Any]
    configured_providers: list[str]
    merged_instructions: list[str]


class ClaudeBaselineConfigComposer:
    def __init__(self, instruction_resolver: OpenCodeInstructionResolver | None = None) -> None:
        self._instruction_resolver = instruction_resolver or OpenCodeInstructionResolver()

    async def _get_provider_api_key(self, provider_id: str, aliases: tuple[str, ...] = ()) -> Optional[str]:
        for candidate in (provider_id, *aliases):
            api_key = await storage_manager.get_api_key(candidate)
            if isinstance(api_key, str) and api_key.strip():
                return api_key.strip()
        return None

    async def _get_enabled_models(self, provider_id: str, aliases: tuple[str, ...], defaults: list[str]) -> list[str]:
        for candidate in (provider_id, *aliases):
            enabled = await storage_manager.get_app_config(f"provider.{candidate}.enabled_models")
            if isinstance(enabled, list) and enabled:
                return [str(item).strip() for item in enabled if str(item).strip()]
        return [str(item).strip() for item in defaults if str(item).strip()]

    @staticmethod
    def _resolve_preferred_model(preferred: str, available: set[str]) -> Optional[str]:
        normalized = preferred.replace(":", "/", 1).strip()
        if normalized in available:
            return normalized
        if "/" not in normalized:
            return None
        provider_id, model_id = normalized.split("/", 1)
        alias = {"gemini": "google", "google": "gemini"}.get(provider_id.strip())
        if not alias:
            return None
        candidate = f"{alias}/{model_id.strip()}"
        return candidate if candidate in available else None

    async def compose(
        self,
        *,
        workspace: Path | None,
        instruction_policy: Dict[str, Any] | None = None,
        startup_context: Dict[str, Any] | None = None,
        rules_dir: Optional[str] = None,
    ) -> ClaudeBaselineComposeResult:
        policy = instruction_policy or {}
        include_shared_rules = bool(policy.get("include_shared_rules", True))
        include_workspace_rules = bool(policy.get("include_workspace_rules", True))
        merged_instructions = self._instruction_resolver.resolve_instructions(
            workspace=workspace,
            include_shared_rules=include_shared_rules,
            include_workspace_rules=include_workspace_rules,
        )

        providers: Dict[str, Any] = {}
        available_models: set[str] = set()
        configured_providers: set[str] = set()
        default_model: Optional[str] = None

        for provider_id, provider in SUPPORTED_PROVIDERS.items():
            aliases: tuple[str, ...] = ("google",) if provider_id == "gemini" else tuple()
            api_key = await self._get_provider_api_key(provider_id, aliases)
            if not api_key:
                continue
            models = await self._get_enabled_models(provider_id, aliases, list(provider.get("models") or []))
            if not models:
                continue
            providers[provider_id] = {
                "configured": True,
                "models": models,
            }
            configured_providers.add(provider_id)
            for item in models:
                available_models.add(f"{provider_id}/{item}")
            if provider_id == "gemini":
                providers["google"] = {
                    "configured": True,
                    "models": list(models),
                }
                configured_providers.add("google")
                for item in models:
                    available_models.add(f"google/{item}")
            if not default_model and models:
                default_model = f"{provider_id}/{models[0]}"

        preferred = await storage_manager.get_config("user_preference:model")
        if isinstance(preferred, str) and preferred.strip():
            resolved = self._resolve_preferred_model(preferred, available_models)
            if resolved:
                default_model = resolved

        default_agent = "build"
        if isinstance(startup_context, dict):
            candidate = str(startup_context.get("default_agent") or "").strip()
            if candidate:
                default_agent = candidate

        config: Dict[str, Any] = {
            "model": default_model or "anthropic/claude-sonnet-4-20250514",
            "default_agent": default_agent,
            "instructions": merged_instructions,
            "providers": providers,
            "permission_mode": "default",
            "setting_sources": ["project"],
            "system_prompt": {"type": "preset", "preset": "claude_code"},
        }
        normalized_rules_dir = str(rules_dir or "").strip()
        if normalized_rules_dir:
            config["rules_dir"] = normalized_rules_dir

        return ClaudeBaselineComposeResult(
            config=config,
            configured_providers=sorted(configured_providers),
            merged_instructions=merged_instructions,
        )
