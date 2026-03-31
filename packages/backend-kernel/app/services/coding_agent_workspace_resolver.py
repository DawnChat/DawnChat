from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.plugins import get_plugin_manager
from app.services.workbench_workspace_service import get_workbench_workspace_service


class WorkspaceResolveError(ValueError):
    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class WorkspaceResolveResult:
    workspace_path: str
    startup_context: Dict[str, Any]
    instruction_policy: Dict[str, Any]


def resolve_coding_agent_workspace(
    *,
    workspace_kind: str,
    plugin_id: Optional[str],
    project_id: Optional[str],
) -> WorkspaceResolveResult:
    normalized_kind = str(workspace_kind or "plugin-dev").strip()
    if normalized_kind == "plugin-dev":
        normalized_plugin_id = str(plugin_id or "").strip()
        if not normalized_plugin_id:
            raise WorkspaceResolveError("plugin_id 不能为空", status_code=400)
        plugin_manager = get_plugin_manager()
        plugin = plugin_manager.get_plugin(normalized_plugin_id)
        if not plugin:
            raise WorkspaceResolveError(f"Plugin not found: {normalized_plugin_id}", status_code=404)
        plugin_path = str(getattr(plugin.manifest, "plugin_path", "") or "")
        if not plugin_path:
            raise WorkspaceResolveError(
                f"Plugin not found or path missing: {normalized_plugin_id}",
                status_code=404,
            )
        workspace_profile = plugin_manager.get_plugin_workspace_profile(normalized_plugin_id) or {}
        instruction_policy = {
            "include_shared_rules": bool(
                getattr(
                    getattr(getattr(plugin.manifest, "opencode", None), "instruction_policy", None),
                    "include_shared_rules",
                    True,
                )
            ),
            "include_workspace_rules": bool(
                getattr(
                    getattr(getattr(plugin.manifest, "opencode", None), "instruction_policy", None),
                    "include_workspace_rules",
                    True,
                )
            ),
        }
        startup_context = {
            "workspace_kind": normalized_kind,
            "plugin_id": normalized_plugin_id,
            "workspace_profile": workspace_profile,
        }
        return WorkspaceResolveResult(
            workspace_path=plugin_path,
            startup_context=startup_context,
            instruction_policy=instruction_policy,
        )

    if normalized_kind == "workbench-general":
        normalized_project_id = str(project_id or "").strip()
        if not normalized_project_id:
            raise WorkspaceResolveError("project_id 不能为空", status_code=400)
        service = get_workbench_workspace_service()
        try:
            workspace_path = service.resolve_workspace_path(normalized_project_id)
            workspace_profile = service.build_workspace_profile(normalized_project_id)
        except FileNotFoundError as err:
            raise WorkspaceResolveError(str(err), status_code=404) from err
        startup_context = {
            "workspace_kind": normalized_kind,
            "project_id": normalized_project_id,
            "workspace_profile": workspace_profile,
        }
        return WorkspaceResolveResult(
            workspace_path=workspace_path,
            startup_context=startup_context,
            instruction_policy={},
        )

    raise WorkspaceResolveError(f"不支持的 workspace_kind: {normalized_kind}", status_code=400)
