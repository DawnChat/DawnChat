from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from typing import Any, AsyncIterator, Dict, List, Optional
import uuid

from app.agentv3.ai.thinking import (
    merge_thinking,
    normalize_budget_tokens,
    normalize_effort,
)
from app.agentv3.event_hub import AgentV3EventHub
from app.agentv3.policy.agent_profile import get_profile_rules
from app.agentv3.policy.config_resolver import AgentV3ConfigResolver
from app.agentv3.policy.permission_engine import PermissionDecision
from app.agentv3.run_coordinator import AgentV3RunCoordinator
from app.agentv3.runtime.loop import RuntimeLoop
from app.agentv3.session_store import AgentV3SessionStore
from app.ai.base import Message
from app.config import Config
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.services.agent_catalog_service import get_agent_catalog_service
from app.services.model_list_service import get_available_models
from app.services.workbench_workspace_service import get_workbench_workspace_service
from app.utils.logger import get_logger

logger = get_logger("agentv3_service")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class AgentV3Service:
    def __init__(self):
        self._store = AgentV3SessionStore()
        self._event_hub = AgentV3EventHub(history_limit=2000)
        self._coordinator = AgentV3RunCoordinator()
        self._sessions = self._store.sessions
        self._messages = self._store.messages
        self._pending_permissions = self._store.pending_permissions
        self._lock = self._store.lock
        self._subscribers = self._event_hub.subscribers
        self._runtime = RuntimeLoop()
        self._running_tasks = self._coordinator.running_tasks
        self._pending_system_prompts: Dict[str, List[str]] = {}
        self._config_resolver = AgentV3ConfigResolver()
        self._agent_catalog = get_agent_catalog_service()
        self._event_seq_by_session = self._event_hub.event_seq_by_session
        self._event_id_counter = self._event_hub.event_id_counter
        self._event_history = self._event_hub.event_history
        self._event_history_limit = self._event_hub.event_history_limit
        self._now_iso = _now_iso
        self._supported_thinking_efforts: List[str] = ["low", "medium", "high", "max"]
        self._stream_heartbeat_ms = 10_000

    def list_agents(self) -> List[Dict[str, Any]]:
        rows = self._agent_catalog.list_agents()
        return [dict(item) for item in rows]

    async def list_models(self) -> List[Dict[str, str]]:
        payload = await get_available_models(caller="agentv3")
        models = payload.get("models", {}) if isinstance(payload, dict) else {}
        rows: List[Dict[str, str]] = []

        local_rows = models.get("local", []) if isinstance(models, dict) else []
        if isinstance(local_rows, list):
            for item in local_rows:
                if not isinstance(item, dict):
                    continue
                provider_id = str(item.get("provider") or "local")
                model_id = str(item.get("id") or "").strip()
                if not provider_id or not model_id:
                    continue
                rows.append(
                    {
                        "id": f"{provider_id}/{model_id}",
                        "label": str(item.get("name") or model_id),
                        "providerID": provider_id,
                        "modelID": model_id,
                    }
                )

        cloud_rows = models.get("cloud", {}) if isinstance(models, dict) else {}
        if isinstance(cloud_rows, dict):
            for provider_id, model_items in cloud_rows.items():
                if not isinstance(model_items, list):
                    continue
                for item in model_items:
                    if not isinstance(item, dict):
                        continue
                    model_key = str(item.get("model_key") or item.get("id") or "").strip()
                    model_id = str(item.get("name") or "").strip()
                    if not model_id and ":" in model_key:
                        model_id = model_key.split(":", 1)[1].strip()
                    if not provider_id or not model_id:
                        continue
                    rows.append(
                        {
                            "id": f"{provider_id}/{model_id}",
                            "label": str(item.get("name") or model_id),
                            "providerID": str(provider_id),
                            "modelID": model_id,
                        }
                    )

        rows.sort(key=lambda item: (item.get("providerID", ""), item.get("label", "")))
        return rows

    async def list_sessions(self) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = list(self._sessions.values())
        return sorted(rows, key=lambda item: item.get("time", {}).get("updated", ""), reverse=True)

    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        async with self._lock:
            row = self._sessions.get(session_id)
            if not row:
                return None
            return dict(row)

    async def create_session(
        self,
        title: Optional[str] = None,
        workspace_path: Optional[str] = None,
        plugin_id: Optional[str] = None,
        project_id: Optional[str] = None,
        workspace_kind: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            await get_opencode_rules_service().ensure_ready(force_refresh=False)
        except Exception as err:
            logger.warning("agentv3 shared opencode config not ready: %s", err)
        resolved_workspace = self._resolve_workspace_binding(
            workspace_path=workspace_path,
            plugin_id=plugin_id,
            project_id=project_id,
        )
        resolved_workspace_path = resolved_workspace["workspace_path"]
        resolved_plugin_id = resolved_workspace["plugin_id"]
        resolved_project_id = resolved_workspace["project_id"]
        resolved_workspace_kind = str(
            workspace_kind
            or ("workbench-general" if resolved_project_id else "plugin-dev" if resolved_plugin_id else "")
        ).strip()
        async with self._lock:
            session_id = _id("ses")
            trace_id = _id("trace")
            now = _now_iso()
            default_agent = self._agent_catalog.resolve_default_agent(resolved_workspace_path)
            row = {
                "id": session_id,
                "title": title or "New Chat",
                "status": "idle",
                "engine": "agentv3",
                "workspace_path": resolved_workspace_path,
                "plugin_id": resolved_plugin_id,
                "project_id": resolved_project_id,
                "workspace_kind": resolved_workspace_kind,
                "config": {
                    "agent": default_agent,
                    "model": self._default_model_selection(),
                    "permission_rules": get_profile_rules(default_agent),
                    "thinking": {"enabled": True, "effort": "medium", "budget_tokens": 0},
                    "max_steps": int(Config.AGENTV3_MAX_STEPS),
                },
                "opencode_config": {"default_agent": default_agent},
                "meta": {
                    "trace_id": trace_id,
                    "session_source": "agentv3_api",
                },
                "time": {"created": now, "updated": now},
            }
            self._sessions[session_id] = row
            self._messages[session_id] = []
        await self._emit("session.created", session_id, properties={"session": dict(row)})
        return row

    async def update_session(self, session_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with self._lock:
            row = self._sessions.get(session_id)
            if not row:
                return None
            if "title" in patch and isinstance(patch["title"], str):
                row["title"] = patch["title"]
            row["time"]["updated"] = _now_iso()
            row["status"] = "idle"
            value = dict(row)
        await self._emit("session.updated", session_id, properties={"session": value})
        return value

    async def delete_session(self, session_id: str) -> bool:
        async with self._lock:
            row = self._sessions.pop(session_id, None)
            self._messages.pop(session_id, None)
        if not row:
            return False
        await self._emit("session.deleted", session_id, properties={"session": row})
        return True

    async def list_messages(self, session_id: str) -> List[Dict[str, Any]]:
        async with self._lock:
            rows = self._messages.get(session_id, [])
            return [json.loads(json.dumps(item)) for item in rows]

    async def update_session_config(
        self,
        session_id: str,
        patch: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        next_agent = patch.get("agent")
        next_model = self._normalize_model_selection(patch.get("model"))
        next_max_steps = self._normalize_max_steps(patch.get("max_steps"))
        opencode_patch = patch.get("opencode") if isinstance(patch.get("opencode"), dict) else {}
        async with self._lock:
            row = self._sessions.get(session_id)
            if not row:
                return None
            config = row.setdefault(
                "config",
                {"agent": str(Config.AGENTV3_DEFAULT_AGENT or "build"), "model": self._default_model_selection()},
            )
            if isinstance(next_agent, str) and next_agent.strip():
                candidate = next_agent.strip()
                workspace_path = str(row.get("workspace_path") or Config.PROJECT_ROOT)
                if not self._agent_catalog.is_primary_visible(candidate, workspace_path):
                    raise ValueError(f"agent not available: {candidate}")
                config["agent"] = candidate
                if not isinstance(config.get("permission_rules"), list):
                    config["permission_rules"] = get_profile_rules(candidate)
            if next_model is not None:
                config["model"] = next_model
            if "permission_rules" in patch and isinstance(patch.get("permission_rules"), list):
                config["permission_rules"] = patch.get("permission_rules")
            if "permission_default_action" in patch and isinstance(patch.get("permission_default_action"), str):
                action = str(patch.get("permission_default_action") or "").strip().lower()
                if action in {"allow", "deny", "ask"}:
                    config["permission_default_action"] = action
            if "thinking" in patch:
                next_thinking = self._normalize_thinking_config(
                    patch.get("thinking"),
                    fallback=config.get("thinking"),
                )
                if next_thinking is not None:
                    config["thinking"] = next_thinking
            if next_max_steps is not None:
                config["max_steps"] = next_max_steps
            if opencode_patch:
                current_open_cfg = row.get("opencode_config")
                if not isinstance(current_open_cfg, dict):
                    current_open_cfg = {}
                merged_open_cfg = dict(current_open_cfg)
                merged_open_cfg.update(opencode_patch)
                row["opencode_config"] = merged_open_cfg
            row["time"]["updated"] = _now_iso()
            value = dict(row)
        await self._emit("session.updated", session_id, properties={"session": value})
        return value

    async def prompt(self, session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        user_msg = await self._append_user_message(session_id, payload)
        if not user_msg:
            return None
        if payload.get("noReply") is True:
            return user_msg
        await self._run_loop_once(session_id)
        rows = await self.list_messages(session_id)
        for msg in reversed(rows):
            info = msg.get("info", {})
            if info.get("role") == "assistant":
                return msg
        return None

    async def prompt_async(self, session_id: str, payload: Dict[str, Any]) -> bool:
        user_msg = await self._append_user_message(session_id, payload)
        if not user_msg:
            return False
        if payload.get("noReply") is True:
            return True
        task = self._running_tasks.get(session_id)
        if task and not task.done():
            return True
        self._running_tasks[session_id] = asyncio.create_task(self._run_loop_once(session_id))
        return True

    async def reply_permission(
        self,
        session_id: str,
        permission_id: str,
        response: PermissionDecision,
        remember: Optional[bool] = None,
    ) -> bool:
        await self._emit(
            "permission.replied",
            session_id,
            properties={
                "sessionID": session_id,
                "requestID": permission_id,
                "reply": response,
                "remember": bool(remember),
            },
        )
        resume_request: Optional[Dict[str, Any]] = None
        async with self._lock:
            request = self._pending_permissions.get(permission_id)
            session_row = self._sessions.get(session_id)
            if request and isinstance(session_row, dict):
                config = session_row.setdefault("config", {})
                if not isinstance(config, dict):
                    config = {}
                    session_row["config"] = config
                if bool(remember) or response in {"always", "reject"}:
                    target = str(request.get("pattern") or "*")
                    tool = str(request.get("tool") or "*")
                    action = "deny" if response == "reject" else "allow"
                    rules = config.get("permission_rules")
                    if not isinstance(rules, list):
                        rules = []
                    rules = [r for r in rules if not (str(r.get("permission") or "") == tool and str(r.get("pattern") or "") == target)]
                    rules.append({"permission": tool, "pattern": target, "action": action})
                    config["permission_rules"] = rules
                self._pending_permissions.pop(permission_id, None)
                if response in {"once", "always"}:
                    resume_request = dict(request)
        if resume_request:
            await self._resume_permission_request(session_id=session_id, request=resume_request)
        return True

    async def interrupt(self, session_id: str) -> bool:
        task = self._running_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
        await self._emit("run.interrupted", session_id, properties={"sessionID": session_id})
        await self._emit("session.idle", session_id, properties={"sessionID": session_id})
        return True

    async def resume(self, session_id: str, payload: Dict[str, Any]) -> bool:
        await self._emit(
            "run.resumed",
            session_id,
            properties={"sessionID": session_id, "payload": payload},
        )
        return True

    async def subscribe_events(self, last_event_id: Optional[int] = None) -> AsyncIterator[Dict[str, Any]]:
        async for event in self._event_hub.subscribe_events(
            lock=self._lock,
            stream_heartbeat_ms=self._stream_heartbeat_ms,
            last_event_id=last_event_id,
        ):
            yield event

    def get_engine_meta(self) -> Dict[str, Any]:
        return {
            "engine": "agentv3",
            "version": "0.1.0",
            "protocol_version": "dep/1",
            "capabilities": {
                "multi_session": True,
                "tool_call_stream": True,
                "permission_flow": True,
                "interrupt_resume": True,
                "structured_output": False,
                "thinking_config": True,
                "thinking_efforts": list(self._supported_thinking_efforts),
                "max_steps_config": True,
                "stream_heartbeat": True,
                "replay_last_event_id": True,
            },
        }

    async def _append_user_message(self, session_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        async with self._lock:
            if session_id not in self._sessions:
                return None
            binding = self._resolve_workspace_binding(
                workspace_path=str(payload.get("workspace_path") or "").strip() or None,
                plugin_id=str(payload.get("plugin_id") or "").strip() or None,
                project_id=str(payload.get("project_id") or "").strip() or None,
            )
            workspace_kind = str(payload.get("workspace_kind") or "").strip()
            if binding["plugin_id"]:
                self._sessions[session_id]["plugin_id"] = binding["plugin_id"]
            if binding["project_id"]:
                self._sessions[session_id]["project_id"] = binding["project_id"]
            if workspace_kind:
                self._sessions[session_id]["workspace_kind"] = workspace_kind
            if binding["workspace_path"]:
                self._sessions[session_id]["workspace_path"] = binding["workspace_path"]
            config = self._sessions[session_id].setdefault(
                "config",
                {"agent": str(Config.AGENTV3_DEFAULT_AGENT or "build"), "model": self._default_model_selection()},
            )
            agent = payload.get("agent")
            if isinstance(agent, str) and agent.strip():
                workspace_path = str(self._sessions[session_id].get("workspace_path") or Config.PROJECT_ROOT)
                candidate = agent.strip()
                if self._agent_catalog.is_primary_visible(candidate, workspace_path):
                    config["agent"] = candidate
            incoming_model = self._normalize_model_selection(payload.get("model"))
            if incoming_model is not None:
                config["model"] = incoming_model
            incoming_thinking = self._normalize_thinking_config(
                payload.get("thinking"),
                fallback=config.get("thinking"),
            )
            if incoming_thinking is not None:
                config["thinking"] = incoming_thinking
            incoming_max_steps = self._normalize_max_steps(payload.get("max_steps"))
            if incoming_max_steps is not None:
                config["max_steps"] = incoming_max_steps
            if payload.get("noReply") is not True:
                system_prompt = str(payload.get("system") or "").strip()
                if system_prompt:
                    queue = self._pending_system_prompts.setdefault(session_id, [])
                    queue.append(system_prompt)
            text = ""
            parts = payload.get("parts", [])
            if isinstance(parts, list) and parts:
                first = parts[0]
                if isinstance(first, dict):
                    text = str(first.get("text", ""))
            message_id = _id("msg")
            part_id = _id("part")
            now = _now_iso()
            msg: Dict[str, Any] = {
                "info": {
                    "id": message_id,
                    "role": "user",
                    "sessionID": session_id,
                    "time": {"created": now, "completed": now},
                    "error": None,
                    "model": config.get("model"),
                    "agent": config.get("agent"),
                },
                "parts": [{"id": part_id, "type": "text", "messageID": message_id, "text": text}],
            }
            self._messages[session_id].append(msg)
            self._sessions[session_id]["time"]["updated"] = now
        first_part = msg["parts"][0] if isinstance(msg.get("parts"), list) and msg["parts"] else {}
        await self._emit("message.updated", session_id, message_id=message_id, properties={"info": msg["info"]})
        await self._emit(
            "message.part.updated",
            session_id,
            message_id=message_id,
            properties={"part": first_part},
        )
        return msg

    def _resolve_workspace_from_plugin(self, plugin_id: str) -> Optional[str]:
        try:
            from app.plugins import get_plugin_manager

            plugin_path = get_plugin_manager().get_plugin_path(plugin_id)
            if not plugin_path:
                return None
            return plugin_path
        except Exception as err:
            logger.warning("resolve plugin workspace failed: %s", err)
            return None

    def _resolve_workspace_from_project(self, project_id: str) -> Optional[str]:
        try:
            return get_workbench_workspace_service().resolve_workspace_path(project_id)
        except Exception as err:
            logger.warning("resolve project workspace failed: %s", err)
            return None

    def _resolve_workspace_binding(
        self,
        *,
        workspace_path: Optional[str] = None,
        plugin_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, str]:
        resolved_workspace_path = str(workspace_path or "").strip()
        resolved_plugin_id = str(plugin_id or "").strip()
        resolved_project_id = str(project_id or "").strip()
        if not resolved_workspace_path and resolved_plugin_id:
            resolved_workspace_path = str(self._resolve_workspace_from_plugin(resolved_plugin_id) or "").strip()
        if not resolved_workspace_path and resolved_project_id:
            resolved_workspace_path = str(self._resolve_workspace_from_project(resolved_project_id) or "").strip()
        if not resolved_workspace_path:
            resolved_workspace_path = str(Config.PROJECT_ROOT)
        return {
            "workspace_path": resolved_workspace_path,
            "plugin_id": resolved_plugin_id,
            "project_id": resolved_project_id,
        }

    async def _run_loop_once(self, session_id: str) -> None:
        trace_id = _id("trace")
        run_id = _id("run")
        await self._coordinator.run_loop_once(self, session_id=session_id, trace_id=trace_id, run_id=run_id)

    async def _resume_permission_request(self, session_id: str, request: Dict[str, Any]) -> None:
        tool_name = str(request.get("tool") or "").strip()
        message_id = str(request.get("messageID") or "")
        part_id = str(request.get("partID") or "")
        call_id = str(request.get("callID") or _id("call"))
        tool_input = request.get("input") if isinstance(request.get("input"), dict) else {}
        if not tool_name or not hasattr(self._runtime, "_registry") or not hasattr(self._runtime, "_tool_executor"):
            task = self._running_tasks.get(session_id)
            if not task or task.done():
                self._running_tasks[session_id] = asyncio.create_task(self._run_loop_once(session_id))
            return
        session = await self.get_session(session_id)
        workspace_path = str((session or {}).get("workspace_path") or Config.PROJECT_ROOT)
        plugin_id = str((session or {}).get("plugin_id") or "")
        if message_id and part_id:
            await self._emit(
                "message.part.updated",
                session_id,
                message_id=message_id,
                properties={
                    "part": self._runtime._build_tool_part(
                        message_id=message_id,
                        part_id=part_id,
                        tool_name=tool_name,
                        call_id=call_id,
                        args=tool_input,
                        status="running",
                        workspace_path=workspace_path,
                    )
                },
            )
        result = await self._runtime._registry.execute(
            tool_name,
            tool_input,
            {"workspace_path": workspace_path, "plugin_id": plugin_id},
        )
        ok = bool(result.get("ok"))
        output_text = self._runtime._tool_executor.tool_result_text(result, tool_name)
        error_text = self._runtime._tool_executor.tool_error_text(result)
        if message_id and part_id:
            await self._emit(
                "message.part.updated",
                session_id,
                message_id=message_id,
                properties={
                    "part": self._runtime._build_tool_part(
                        message_id=message_id,
                        part_id=part_id,
                        tool_name=tool_name,
                        call_id=call_id,
                        args=tool_input,
                        status="completed" if ok else "error",
                        output=output_text,
                        error=None if ok else error_text,
                        workspace_path=workspace_path,
                    )
                },
            )
            await self._emit(
                "tool.result" if ok else "tool.error",
                session_id,
                message_id=message_id,
                properties={
                    "sessionID": session_id,
                    "messageID": message_id,
                    "partID": part_id,
                    "tool": tool_name,
                    "callID": call_id,
                    "ok": ok,
                    "output": output_text if ok else "",
                    "error": None if ok else error_text,
                },
            )
        if not ok:
            await self._emit(
                "session.error",
                session_id,
                properties={
                    "sessionID": session_id,
                    "message": f"permission approved but tool failed: {tool_name}",
                    "detail": error_text,
                },
            )
            return
        await self._append_tool_result_message(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            output_text=output_text,
            workspace_path=workspace_path,
        )
        task = self._running_tasks.get(session_id)
        if not task or task.done():
            self._running_tasks[session_id] = asyncio.create_task(self._run_loop_once(session_id))

    async def _append_tool_result_message(
        self,
        *,
        session_id: str,
        tool_name: str,
        call_id: str,
        output_text: str,
        workspace_path: str,
    ) -> None:
        message_id = _id("msg")
        part_id = _id("part")
        now = _now_iso()
        info = {
            "id": message_id,
            "role": "tool",
            "sessionID": session_id,
            "time": {"created": now, "completed": now},
            "error": None,
        }
        part = {
            "id": part_id,
            "type": "tool",
            "messageID": message_id,
            "tool": tool_name,
            "callID": call_id,
            "state": {
                "status": "completed",
                "output": output_text,
                "workspacePath": workspace_path,
            },
        }
        async with self._lock:
            rows = self._messages.setdefault(session_id, [])
            rows.append({"info": info, "parts": [part]})
            if session_id in self._sessions:
                self._sessions[session_id]["time"]["updated"] = now
        await self._emit("message.updated", session_id, message_id=message_id, properties={"info": info})
        await self._emit("message.part.updated", session_id, message_id=message_id, properties={"part": part})

    def _resolve_model_key(self, session_id: str, session_row: Optional[Dict[str, Any]] = None) -> str:
        row = session_row or self._sessions.get(session_id, {})
        if isinstance(row, dict):
            config = row.get("config")
            if isinstance(config, dict):
                model = self._normalize_model_selection(config.get("model"))
                if model:
                    return f"{model['providerID']}:{model['modelID']}"
        rows = self._messages.get(session_id, [])
        for msg in reversed(rows):
            info = msg.get("info", {})
            if info.get("role") != "user":
                continue
            model = self._normalize_model_selection(info.get("model"))
            if model:
                return f"{model['providerID']}:{model['modelID']}"
        return "default"

    def _default_model_selection(self) -> Optional[Dict[str, str]]:
        value = str(Config.DEFAULT_MODEL or "").strip()
        if not value:
            return None
        if ":" in value:
            provider_id, model_id = value.split(":", 1)
            provider_id = provider_id.strip()
            model_id = model_id.strip()
            if provider_id and model_id:
                return {"providerID": provider_id, "modelID": model_id}
        return {"providerID": "local", "modelID": value}

    def _normalize_model_selection(self, value: Any) -> Optional[Dict[str, str]]:
        if isinstance(value, dict):
            provider_id = str(value.get("providerID") or value.get("provider") or "").strip()
            model_id = str(value.get("modelID") or value.get("model") or "").strip()
            if provider_id and model_id:
                return {"providerID": provider_id, "modelID": model_id}
            return None
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            if ":" in raw:
                provider_id, model_id = raw.split(":", 1)
                provider_id = provider_id.strip()
                model_id = model_id.strip()
                if provider_id and model_id:
                    return {"providerID": provider_id, "modelID": model_id}
            if "/" in raw:
                provider_id, model_id = raw.split("/", 1)
                provider_id = provider_id.strip()
                model_id = model_id.strip()
                if provider_id and model_id:
                    return {"providerID": provider_id, "modelID": model_id}
        return None

    def _normalize_max_steps(self, value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return parsed

    def _build_runtime_messages(
        self,
        session_id: str,
        workspace_path: str,
        system_instructions: Optional[List[str]] = None,
    ) -> List[Message]:
        rows = self._messages.get(session_id, [])
        model_messages: List[Message] = [
            Message(
                role="system",
                content=(
                    "Current workspace: "
                    f"{workspace_path}\nUse this as your working directory for relative paths and tool calls."
                ),
            )
        ]
        if isinstance(system_instructions, list):
            for item in system_instructions:
                if not isinstance(item, str):
                    continue
                content = item.strip()
                if not content:
                    continue
                model_messages.append(Message(role="system", content=content))
        has_pending_tool_calls = False
        for msg in rows:
            info = msg.get("info", {})
            role = str(info.get("role") or "")
            parts = msg.get("parts", [])
            if role not in {"user", "assistant", "tool"}:
                continue
            if role == "tool":
                if not has_pending_tool_calls:
                    # Defensive filter: ignore orphan tool messages which can break providers like Gemini.
                    continue
                tool_call_id = ""
                content = ""
                for part in parts:
                    if part.get("type") != "tool":
                        continue
                    tool_call_id = str(part.get("callID") or "")
                    output = part.get("state", {}).get("output")
                    if output:
                        content = str(output)
                        break
                if not tool_call_id:
                    continue
                model_messages.append(Message(role="tool", content=content, tool_call_id=tool_call_id))
                has_pending_tool_calls = False
                continue

            text_parts: List[str] = []
            tool_calls: List[Dict[str, Any]] = []
            for part in parts:
                part_type = str(part.get("type") or "")
                if part_type in {"text", "reasoning"}:
                    text_parts.append(str(part.get("text") or ""))
                    continue
                if part_type != "tool":
                    continue
                call_id = str(part.get("callID") or "")
                tool_name = str(part.get("tool") or "")
                raw_input = part.get("state", {}).get("input")
                arguments = self._normalize_tool_arguments(raw_input)
                if not tool_name:
                    continue
                tool_calls.append(
                    {
                        "id": call_id or _id("call"),
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(arguments, ensure_ascii=False),
                        },
                    }
                )

            model_messages.append(
                Message(
                    role=role,
                    content="\n".join(tp for tp in text_parts if tp),
                    tool_calls=tool_calls or None,
                )
            )
            has_pending_tool_calls = bool(tool_calls)
        return model_messages

    def _resolve_permission_rules(self, session_row: Dict[str, Any]) -> List[Dict[str, str]]:
        config = session_row.get("config")
        profile = str(Config.AGENTV3_DEFAULT_AGENT or "build")
        merged = get_profile_rules(profile)
        if not isinstance(config, dict):
            return merged
        custom = config.get("permission_rules")
        if isinstance(custom, list):
            for item in custom:
                if not isinstance(item, dict):
                    continue
                permission = str(item.get("permission") or "").strip()
                pattern = str(item.get("pattern") or "").strip()
                action = str(item.get("action") or "").strip().lower()
                if not permission or not pattern or action not in {"allow", "deny", "ask"}:
                    continue
                merged.append({"permission": permission, "pattern": pattern, "action": action})
        return merged

    def resolve_session_runtime_config(
        self,
        *,
        session_row: Dict[str, Any],
        workspace_path: str,
    ) -> Dict[str, Any]:
        shared_dir = get_opencode_rules_service().get_current_dir()
        return self._config_resolver.resolve(
            session_row=session_row,
            workspace_path=workspace_path,
            default_model=self._default_model_selection(),
            shared_config_dir=shared_dir,
        )

    def _resolve_thinking_config(self, session_row: Dict[str, Any]) -> Dict[str, Any]:
        model_key = self._resolve_model_key("", session_row)
        config = session_row.get("config")
        raw = config.get("thinking") if isinstance(config, dict) else None
        if isinstance(raw, dict):
            is_legacy_default = (
                raw.get("enabled") is False
                and normalize_effort(raw.get("effort"), default="medium") == "medium"
                and normalize_budget_tokens(raw.get("budget_tokens"), default=0) == 0
            )
            if is_legacy_default:
                # Backward compatibility: historical default accidentally disabled thinking.
                raw = {"enabled": True, "effort": "medium", "budget_tokens": 0}
        merged = merge_thinking(model_key=model_key, override=raw if isinstance(raw, dict) else None)
        return merged.to_dict()

    def _normalize_thinking_config(
        self,
        raw: Any,
        fallback: Any = None,
    ) -> Optional[Dict[str, Any]]:
        if raw is None and fallback is None:
            return None
        source = raw if isinstance(raw, dict) else fallback
        if not isinstance(source, dict):
            return None
        effort = normalize_effort(source.get("effort"), default="medium")
        budget_tokens = normalize_budget_tokens(source.get("budget_tokens"), default=0)
        return {
            "enabled": bool(source.get("enabled")),
            "effort": effort,
            "budget_tokens": budget_tokens,
        }

    def _normalize_tool_arguments(self, raw_input: Any) -> Dict[str, Any]:
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str):
            try:
                parsed = json.loads(raw_input)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    async def _apply_event_to_store(self, event: Dict[str, Any]) -> None:
        await self._event_hub.apply_event_to_store(
            event,
            lock=self._lock,
            sessions=self._sessions,
            messages=self._messages,
            now_iso=self._now_iso,
        )

    def _find_message_index(self, rows: List[Dict[str, Any]], message_id: str) -> int:
        return self._event_hub._find_message_index(rows, message_id)

    def _find_part_index(self, parts: List[Dict[str, Any]], part_id: str) -> int:
        return self._event_hub._find_part_index(parts, part_id)

    async def _emit(
        self,
        event_type: str,
        session_id: str,
        message_id: Optional[str] = None,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        await self._event_hub.emit(
            event_type=event_type,
            session_id=session_id,
            message_id=message_id,
            properties=properties,
            lock=self._lock,
            apply_to_store=self._apply_event_to_store,
        )

    async def _stamp_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return await self._event_hub.stamp_event(event, lock=self._lock)


_service_instance: AgentV3Service | None = None


def get_agentv3_service() -> AgentV3Service:
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentV3Service()
    return _service_instance
