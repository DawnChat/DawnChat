from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import quote

from app.config import Config
from app.services.model_list_service import SUPPORTED_PROVIDERS
from app.services.opencode_instruction_resolver import OpenCodeInstructionResolver
from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("opencode_baseline_config_composer")

MCP_DESCRIPTION_INSTRUCTION = (
    "When calling DawnChat MCP tools (for example dawnchat_ui_bridge_*), "
    "always provide a concise 'description' argument in 5-12 words that states the user-facing intent."
)


@dataclass
class BaselineComposeResult:
    config: Dict[str, Any]
    configured_providers: list[str]
    merged_instructions: list[str]


class OpenCodeBaselineConfigComposer:
    def __init__(self, instruction_resolver: OpenCodeInstructionResolver | None = None) -> None:
        self._instruction_resolver = instruction_resolver or OpenCodeInstructionResolver()

    async def _get_provider_api_key(self, provider_id: str, aliases: tuple[str, ...] = ()) -> Optional[str]:
        for candidate in (provider_id, *aliases):
            api_key = await storage_manager.get_marked_api_key(candidate)
            if isinstance(api_key, str) and api_key.strip():
                return api_key.strip()
        return None

    async def _get_enabled_models(
        self,
        provider_id: str,
        aliases: tuple[str, ...],
        default_models: Sequence[str],
    ) -> list[str]:
        for candidate in (provider_id, *aliases):
            enabled_models = await storage_manager.get_app_config(f"provider.{candidate}.enabled_models")
            if isinstance(enabled_models, list) and enabled_models:
                return [str(item) for item in enabled_models if str(item).strip()]
        return list(default_models)

    async def _resolve_provider_base_url(
        self,
        provider_id: str,
        aliases: tuple[str, ...],
        provider: Dict[str, Any],
    ) -> Optional[str]:
        for candidate in (provider_id, *aliases):
            base_url = await storage_manager.get_app_config(f"provider.{candidate}.base_url")
            if isinstance(base_url, str) and base_url.strip():
                return base_url.strip()
        if provider.get("openai_compatible"):
            default_base_url = provider.get("default_base_url")
            if isinstance(default_base_url, str) and default_base_url.strip():
                return default_base_url.strip()
        return None

    @staticmethod
    def _resolve_preferred_model(preferred: str, available_models: set[str]) -> Optional[str]:
        preferred_key = preferred.replace(":", "/", 1)
        if preferred_key in available_models:
            return preferred_key
        if "/" not in preferred_key:
            return None
        provider_id, model_id = preferred_key.split("/", 1)
        alias_pairs = {
            "gemini": "google",
            "google": "gemini",
        }
        alias_provider = alias_pairs.get(provider_id)
        if not alias_provider:
            return None
        alias_key = f"{alias_provider}/{model_id}"
        return alias_key if alias_key in available_models else None

    async def compose(
        self,
        *,
        host: str,
        port: int,
        workspace: Path | None,
        instruction_policy: Dict[str, Any] | None = None,
        startup_context: Dict[str, Any] | None = None,
    ) -> BaselineComposeResult:
        mcp_timeout_ms = max(1, int(Config.MCP_PROXY_TIMEOUT_READ_SECONDS * 1000))
        search_timeout_ms = max(1, int(Config.OPENCODE_SEARCH_TIMEOUT_READ_SECONDS * 1000))
        ui_bridge_mcp_timeout_ms = max(1, int(Config.OPENCODE_UI_BRIDGE_MCP_TIMEOUT_READ_SECONDS * 1000))
        policy = instruction_policy or {}
        include_shared_rules = bool(policy.get("include_shared_rules", True))
        include_workspace_rules = bool(
            policy.get("include_workspace_rules", Config.OPENCODE_INCLUDE_WORKSPACE_RULES)
        )
        merged_instructions = self._instruction_resolver.resolve_instructions(
            workspace=workspace,
            include_shared_rules=include_shared_rules,
            include_workspace_rules=include_workspace_rules,
        )
        if MCP_DESCRIPTION_INSTRUCTION not in merged_instructions:
            merged_instructions.append(MCP_DESCRIPTION_INSTRUCTION)
        provider_cfg: Dict[str, Any] = {}
        default_model: Optional[str] = None
        available_models: set[str] = set()
        configured_providers: set[str] = set()
        marked_provider_ids = set(await storage_manager.list_providers_with_key_marker())
        marker_candidate_count = 0

        for provider_id, provider in SUPPORTED_PROVIDERS.items():
            aliases: tuple[str, ...] = ("google",) if provider_id == "gemini" else ()
            candidates = (provider_id, *aliases)
            if not any(candidate in marked_provider_ids for candidate in candidates):
                continue
            marker_candidate_count += 1
            api_key = await self._get_provider_api_key(provider_id, aliases)
            if not api_key:
                continue
            models = await self._get_enabled_models(provider_id, aliases, provider["models"])
            options: Dict[str, Any] = {"apiKey": api_key}
            resolved_base_url = await self._resolve_provider_base_url(provider_id, aliases, provider)
            if resolved_base_url:
                options["baseURL"] = resolved_base_url
            provider_ids = [provider_id, "google"] if provider_id == "gemini" else [provider_id]
            for resolved_provider_id in provider_ids:
                provider_cfg[resolved_provider_id] = {
                    "options": dict(options),
                }
                configured_providers.add(resolved_provider_id)
            for model in models:
                available_models.add(f"{provider_id}/{model}")
                if provider_id == "gemini":
                    available_models.add(f"google/{model}")
            if not default_model and models:
                default_model = f"{provider_id}/{models[0]}"

        preferred = await storage_manager.get_config("user_preference:model")
        if isinstance(preferred, str) and preferred:
            preferred_model = self._resolve_preferred_model(preferred, available_models)
            if preferred_model:
                default_model = preferred_model

        baseline: Dict[str, Any] = {
            "$schema": "https://opencode.ai/config.json",
            "model": default_model or "openai/gpt-4o-mini",
            "default_agent": "build",
            "instructions": merged_instructions,
            "server": {
                "port": port,
                "hostname": host,
                "cors": [
                    "http://localhost:5173",
                    "http://127.0.0.1:5173",
                    "tauri://localhost",
                    "https://tauri.localhost",
                ],
            },
            "lsp": {
                "vue": {
                    "disabled": True,
                },
            },
            "permission": {
                "edit": "ask",
                "bash": {
                    "*": "ask",
                    "rm *": "deny",
                    "git push *": "deny",
                },
                "external_directory": "ask",
                "doom_loop": "ask",
                "skill": {
                    "*": "allow",
                    "experimental-*": "ask",
                },
            },
            "agent": {
                "plan": {
                    "permission": {
                        "edit": "deny",
                        "bash": "deny",
                    },
                },
                "build": {
                    "permission": {
                        "edit": "allow",
                        "bash": {
                            "*": "ask",
                            "pnpm *": "allow",
                            "npm run *": "allow",
                            "pytest *": "allow",
                            "ruff *": "allow",
                            "vite *": "allow",
                            "python -m pytest *": "allow",
                            "git status*": "allow",
                            "grep *": "allow",
                            "rm *": "deny",
                            "git push *": "deny",
                        },
                    },
                },
            },
            "provider": provider_cfg,
            "mcp": {
                "dawnchat_ui_bridge": {
                    "type": "remote",
                    "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/ui",
                    "enabled": True,
                    "oauth": False,
                    "timeout": max(mcp_timeout_ms, ui_bridge_mcp_timeout_ms),
                    "headers": {"X-DawnChat-MCP": "ui-bridge"},
                },
                "dawnchat_iwp": {
                    "type": "remote",
                    "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/iwp",
                    "enabled": True,
                    "oauth": False,
                    "timeout": mcp_timeout_ms,
                    "headers": {"X-DawnChat-MCP": "iwp"},
                },
                "dawnchat_voice": {
                    "type": "remote",
                    "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/voice",
                    "enabled": True,
                    "oauth": False,
                    "timeout": mcp_timeout_ms,
                    "headers": {"X-DawnChat-MCP": "voice"},
                },
                "dawnchat_search": {
                    "type": "remote",
                    "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/search",
                    "enabled": True,
                    "oauth": False,
                    "timeout": search_timeout_ms,
                    "headers": {"X-DawnChat-MCP": "search"},
                },
            },
        }
        context = startup_context or {}
        plugin_id = str(context.get("plugin_id") or "").strip()
        workspace_kind = str(context.get("workspace_kind") or "").strip().lower()
        effective_plugin_id = plugin_id or "__default_plugin__"
        encoded_plugin_id = quote(effective_plugin_id, safe="")
        baseline["mcp"]["dawnchat_plugin_backend"] = {
            "type": "remote",
            "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/plugin/{encoded_plugin_id}/backend",
            "enabled": True,
            "oauth": False,
            "timeout": mcp_timeout_ms,
            "headers": {
                "X-DawnChat-MCP": "plugin-backend-proxy",
                "X-DawnChat-Plugin-ID": effective_plugin_id,
            },
        }
        baseline["mcp"]["dawnchat_plugin_python"] = {
            "type": "remote",
            "url": f"http://127.0.0.1:{Config.API_PORT}/api/opencode/mcp/plugin/{encoded_plugin_id}/python",
            "enabled": True,
            "oauth": False,
            "timeout": mcp_timeout_ms,
            "headers": {
                "X-DawnChat-MCP": "plugin-python-proxy",
                "X-DawnChat-Plugin-ID": effective_plugin_id,
            },
        }
        logger.info(
            "OpenCode plugin MCP injected: workspace_kind=%s plugin_id=%s effective_plugin_id=%s default_injected=%s mcp_entries=%s",
            workspace_kind,
            plugin_id,
            effective_plugin_id,
            plugin_id != effective_plugin_id,
            ["dawnchat_plugin_backend", "dawnchat_plugin_python"],
        )
        logger.info(
            "OpenCode provider config built: markers=%s marker_candidates=%s configured=%s",
            len(marked_provider_ids),
            marker_candidate_count,
            len(configured_providers),
        )
        return BaselineComposeResult(
            config=baseline,
            configured_providers=sorted(configured_providers),
            merged_instructions=merged_instructions,
        )
