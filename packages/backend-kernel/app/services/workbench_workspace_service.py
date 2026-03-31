from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any, Dict, List, Optional
import uuid

from app.config import Config
from app.utils.logger import get_logger

logger = get_logger("workbench_workspace_service")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_project_id(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        raise ValueError("project_id 不能为空")
    if any(char in candidate for char in ("/", "\\", "..")):
        raise ValueError("project_id 非法")
    return candidate


@dataclass
class WorkbenchProjectRecord:
    id: str
    name: str
    project_type: str
    workspace_path: str
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "project_type": self.project_type,
            "workspace_path": self.workspace_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WorkbenchWorkspaceService:
    METADATA_RELATIVE_PATH = Path(".dawnchat") / "project.json"
    DEFAULT_PROJECT_TYPE = "chat"

    def __init__(self) -> None:
        self._root_dir = Path(Config.WORKBENCH_PROJECTS_DIR).expanduser()

    @property
    def root_dir(self) -> Path:
        self._root_dir.mkdir(parents=True, exist_ok=True)
        return self._root_dir

    def list_projects(self) -> List[Dict[str, Any]]:
        projects: List[WorkbenchProjectRecord] = []
        for child in self.root_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                projects.append(self._read_project(child))
            except Exception as err:
                logger.warning("读取 Workbench 项目失败: %s (%s)", child, err)
        projects.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.to_dict() for item in projects]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists() or not project_dir.is_dir():
            return None
        return self._read_project(project_dir).to_dict()

    def create_project(
        self,
        *,
        name: Optional[str] = None,
        project_type: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = _now_iso()
        resolved_project_id = _safe_project_id(project_id) if project_id else f"proj_{uuid.uuid4().hex[:12]}"
        project_dir = self._project_dir(resolved_project_id)
        if project_dir.exists():
            raise ValueError(f"project 已存在: {resolved_project_id}")
        project_dir.mkdir(parents=True, exist_ok=False)
        record = WorkbenchProjectRecord(
            id=resolved_project_id,
            name=str(name or resolved_project_id).strip() or resolved_project_id,
            project_type=str(project_type or self.DEFAULT_PROJECT_TYPE).strip() or self.DEFAULT_PROJECT_TYPE,
            workspace_path=str(project_dir),
            created_at=now,
            updated_at=now,
        )
        self._write_project_meta(project_dir, record)
        return record.to_dict()

    def update_project(
        self,
        project_id: str,
        *,
        name: Optional[str] = None,
        project_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists() or not project_dir.is_dir():
            raise FileNotFoundError(f"project 不存在: {project_id}")
        current = self._read_project(project_dir)
        next_record = WorkbenchProjectRecord(
            id=current.id,
            name=str(name).strip() if name is not None and str(name).strip() else current.name,
            project_type=str(project_type).strip() if project_type is not None and str(project_type).strip() else current.project_type,
            workspace_path=current.workspace_path,
            created_at=current.created_at,
            updated_at=_now_iso(),
        )
        self._write_project_meta(project_dir, next_record)
        return next_record.to_dict()

    def delete_project(self, project_id: str) -> bool:
        project_dir = self._project_dir(project_id)
        if not project_dir.exists() or not project_dir.is_dir():
            return False
        shutil.rmtree(project_dir)
        return True

    def resolve_workspace_path(self, project_id: str) -> str:
        project = self.get_project(project_id)
        if not project:
            raise FileNotFoundError(f"project 不存在: {project_id}")
        return str(project.get("workspace_path") or "")

    def build_workspace_profile(self, project_id: str) -> Dict[str, Any]:
        project = self.get_project(project_id)
        if not project:
            raise FileNotFoundError(f"project 不存在: {project_id}")
        workspace_path = str(project.get("workspace_path") or "")
        return {
            "id": f"workbench:{project['id']}",
            "kind": "workbench-general",
            "display_name": project["name"],
            "app_type": project.get("project_type") or self.DEFAULT_PROJECT_TYPE,
            "workspace_path": workspace_path,
            "preferred_entry": "",
            "preferred_directories": [workspace_path] if workspace_path else [],
            "hints": [
                "当前场景是 DawnChat Workbench 通用聊天模式。",
                "优先基于用户当前上下文给出通用协助，不要假设存在插件开发预览或源码圈选能力。",
            ],
            "default_agent": "general",
            "session_strategy": "single",
            "project_id": project["id"],
        }

    def _project_dir(self, project_id: str) -> Path:
        return self.root_dir / _safe_project_id(project_id)

    def _metadata_path(self, project_dir: Path) -> Path:
        return project_dir / self.METADATA_RELATIVE_PATH

    def _read_project(self, project_dir: Path) -> WorkbenchProjectRecord:
        metadata_path = self._metadata_path(project_dir)
        payload: Dict[str, Any] = {}
        if metadata_path.exists():
            payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        stat = project_dir.stat()
        created_at = str(payload.get("created_at") or datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc).isoformat())
        updated_at = str(payload.get("updated_at") or datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat())
        return WorkbenchProjectRecord(
            id=str(payload.get("id") or project_dir.name),
            name=str(payload.get("name") or project_dir.name),
            project_type=str(payload.get("project_type") or self.DEFAULT_PROJECT_TYPE),
            workspace_path=str(project_dir),
            created_at=created_at,
            updated_at=updated_at,
        )

    def _write_project_meta(self, project_dir: Path, record: WorkbenchProjectRecord) -> None:
        metadata_path = self._metadata_path(project_dir)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(
            json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


_service: Optional[WorkbenchWorkspaceService] = None


def get_workbench_workspace_service() -> WorkbenchWorkspaceService:
    global _service
    if _service is None:
        _service = WorkbenchWorkspaceService()
    return _service
