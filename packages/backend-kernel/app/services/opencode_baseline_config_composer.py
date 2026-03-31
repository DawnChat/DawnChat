from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from urllib.parse import quote

from app.config import Config
from app.services.model_list_service import SUPPORTED_PROVIDERS
from app.services.model_manager import get_model_manager
from app.services.opencode_instruction_resolver import OpenCodeInstructionResolver
from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("opencode_baseline_config_composer")


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
            api_key = await storage_manager.get_api_key(candidate)
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
        provider_cfg: Dict[str, Any] = {}
        default_model: Optional[str] = None
        available_models: set[str] = set()
        configured_providers: set[str] = set()

        for provider_id, provider in SUPPORTED_PROVIDERS.items():
            aliases: tuple[str, ...] = ("google",) if provider_id == "gemini" else ()
            api_key = await self._get_provider_api_key(provider_id, aliases)
            if not api_key:
                continue
            models = await self._get_enabled_models(provider_id, aliases, provider["models"])
            if not models:
                continue
            model_map = {m: {"name": m} for m in models}
            options: Dict[str, Any] = {"apiKey": api_key}
            for candidate in (provider_id, *aliases):
                base_url = await storage_manager.get_app_config(f"provider.{candidate}.base_url")
                if isinstance(base_url, str) and base_url.strip():
                    options["baseURL"] = base_url.strip()
                    break
            provider_ids = [provider_id, "google"] if provider_id == "gemini" else [provider_id]
            for resolved_provider_id in provider_ids:
                provider_cfg[resolved_provider_id] = {
                    "models": model_map,
                    "options": dict(options),
                }
                configured_providers.add(resolved_provider_id)
                for model in models:
                    available_models.add(f"{resolved_provider_id}/{model}")
            if not default_model and models:
                default_model = f"{provider_id}/{models[0]}"

        local_provider_id = "dawnchat-local"
        local_models = get_model_manager().get_installed_models()
        if local_models:
            local_map = {}
            for item in local_models:
                model_id = item.get("id")
                if not model_id:
                    continue
                display_name = item.get("name") or item.get("filename") or model_id
                local_map[str(model_id)] = {"name": str(display_name)}
            if local_map:
                provider_cfg[local_provider_id] = {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "DawnChat Local",
                    "options": {
                        "baseURL": Config.get_llama_server_api_base(),
                        "apiKey": "not-needed",
                    },
                    "models": local_map,
                }
                if not default_model:
                    first_local = next(iter(local_map.keys()))
                    default_model = f"{local_provider_id}/{first_local}"
                configured_providers.add(local_provider_id)
                for model in local_map.keys():
                    available_models.add(f"{local_provider_id}/{model}")

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
                    "timeout": mcp_timeout_ms,
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
        return BaselineComposeResult(
            config=baseline,
            configured_providers=sorted(configured_providers),
            merged_instructions=merged_instructions,
        )
