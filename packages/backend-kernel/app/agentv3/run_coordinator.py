from __future__ import annotations

import asyncio
from typing import Dict

from app.agentv3.runtime.loop import RuntimeLoopInput
from app.config import Config
from app.plugins.opencode_rules_service import get_opencode_rules_service
from app.utils.logger import get_logger

logger = get_logger("agentv3_run_coordinator")


class AgentV3RunCoordinator:
    def __init__(self):
        self.running_tasks: Dict[str, asyncio.Task[None]] = {}

    async def run_loop_once(self, service, session_id: str, trace_id: str, run_id: str) -> None:
        try:
            await get_opencode_rules_service().ensure_ready(force_refresh=False)
        except Exception as err:
            logger.warning("agentv3 shared opencode config ensure failed: %s", err)
        async with service._lock:
            if session_id not in service._sessions:
                return
            session_row = service._sessions[session_id]
            workspace_path = str(session_row.get("workspace_path") or Config.PROJECT_ROOT)
            plugin_id = str(session_row.get("plugin_id") or "").strip()
            resolved_config = service.resolve_session_runtime_config(session_row=session_row, workspace_path=workspace_path)
            pending_system = service._pending_system_prompts.pop(session_id, [])
            resolved_system = resolved_config.get("system_instructions") if isinstance(resolved_config, dict) else []
            merged_system_instructions = list(resolved_system) if isinstance(resolved_system, list) else []
            if isinstance(pending_system, list):
                merged_system_instructions.extend([item for item in pending_system if isinstance(item, str) and item.strip()])
            session_row["config"] = {
                **(session_row.get("config") if isinstance(session_row.get("config"), dict) else {}),
                **{k: v for k, v in resolved_config.items() if k != "_source"},
            }
            model_key = service._resolve_model_key(session_id, session_row)
            messages = service._build_runtime_messages(
                session_id,
                workspace_path,
                system_instructions=merged_system_instructions,
            )
            permission_rules = list(resolved_config.get("permission_rules") or service._resolve_permission_rules(session_row))
            thinking_config = resolved_config.get("thinking") or service._resolve_thinking_config(session_row)
            session_config = resolved_config
            max_steps = int(Config.AGENTV3_MAX_STEPS)
            if isinstance(session_config, dict):
                max_steps = service._normalize_max_steps(session_config.get("max_steps")) or max_steps
            permission_default_action = str(
                (resolved_config.get("permission_default_action") if isinstance(resolved_config, dict) else None)
                or getattr(Config, "AGENTV3_PERMISSION_DEFAULT_ACTION", "ask")
            ).lower()
            service._sessions[session_id]["status"] = "running"
        logger.info(
            "agentv3 run start session=%s trace_id=%s run_id=%s model=%s workspace=%s max_steps=%s thinking=%s effort=%s budget=%s perm_default=%s config_source=%s",
            session_id,
            trace_id,
            run_id,
            model_key,
            workspace_path,
            max_steps,
            thinking_config.get("enabled"),
            thinking_config.get("effort"),
            thinking_config.get("budget_tokens"),
            permission_default_action,
            (resolved_config.get("_source") if isinstance(resolved_config, dict) else {}),
        )
        try:
            async for event in service._runtime.run(
                RuntimeLoopInput(
                    session_id=session_id,
                    workspace_path=workspace_path,
                    messages=messages,
                    plugin_id=plugin_id or None,
                    model=model_key,
                    max_steps=max_steps,
                    trace_id=trace_id,
                    run_id=run_id,
                    permission_rules=permission_rules,
                    permission_default_action=permission_default_action,
                    thinking_enabled=bool(thinking_config.get("enabled")),
                    thinking_effort=(str(thinking_config.get("effort") or "").strip().lower() or None),
                    thinking_budget_tokens=(
                        int(thinking_config.get("budget_tokens"))
                        if isinstance(thinking_config.get("budget_tokens"), int)
                        else None
                    ),
                )
            ):
                stamped = await service._event_hub.stamp_event(event, lock=service._lock)
                await service._event_hub.apply_event_to_store(
                    stamped,
                    lock=service._lock,
                    sessions=service._sessions,
                    messages=service._messages,
                    now_iso=service._now_iso,
                )
                if event.get("type") == "permission.asked":
                    permission = (stamped.get("properties") or {}).get("permission")
                    if isinstance(permission, dict):
                        request_id = str(permission.get("id") or "").strip()
                        if request_id:
                            service._pending_permissions[request_id] = {
                                "tool": str(permission.get("tool") or ""),
                                "pattern": str(permission.get("pattern") or "*"),
                                "sessionID": session_id,
                                "messageID": str(permission.get("messageID") or ""),
                                "callID": str(permission.get("callID") or ""),
                                "partID": str(permission.get("partID") or ""),
                                "input": permission.get("input") if isinstance(permission.get("input"), dict) else {},
                            }
                for queue in list(service._subscribers):
                    try:
                        queue.put_nowait(stamped)
                    except Exception as err:
                        logger.warning("agentv3 queue put failed: %s", err)
        except asyncio.CancelledError:
            logger.info("agentv3 runtime cancelled: %s trace_id=%s run_id=%s", session_id, trace_id, run_id)
            await service._emit("session.idle", session_id, properties={"sessionID": session_id})
        except Exception as err:
            logger.error(
                "agentv3 runtime error: %s trace_id=%s run_id=%s",
                err,
                trace_id,
                run_id,
                exc_info=True,
            )
            await service._emit(
                "session.error",
                session_id,
                properties={"sessionID": session_id, "message": str(err)},
            )
            await service._emit("session.idle", session_id, properties={"sessionID": session_id})
        finally:
            logger.info("agentv3 run finish session=%s trace_id=%s run_id=%s", session_id, trace_id, run_id)
            async with service._lock:
                if session_id in service._sessions:
                    service._sessions[session_id]["status"] = "idle"
                    service._sessions[session_id]["time"]["updated"] = service._now_iso()
            self.running_tasks.pop(session_id, None)
