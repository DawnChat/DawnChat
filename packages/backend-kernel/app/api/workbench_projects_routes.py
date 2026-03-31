from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.workbench_workspace_service import get_workbench_workspace_service
from app.utils.logger import api_logger as logger

router = APIRouter(prefix="/workbench/projects", tags=["workbench-projects"])


class ProjectCreateRequest(BaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None


class ProjectPatchRequest(BaseModel):
    name: Optional[str] = None
    project_type: Optional[str] = None


@router.get("")
async def list_projects() -> Dict[str, Any]:
    service = get_workbench_workspace_service()
    return {"status": "success", "data": service.list_projects()}


@router.post("")
async def create_project(request: ProjectCreateRequest) -> Dict[str, Any]:
    service = get_workbench_workspace_service()
    try:
        project = service.create_project(name=request.name, project_type=request.project_type)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    logger.info("workbench project created: %s", project["id"])
    return {"status": "success", "data": project}


@router.get("/{project_id}")
async def get_project(project_id: str) -> Dict[str, Any]:
    service = get_workbench_workspace_service()
    project = service.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return {"status": "success", "data": project}


@router.patch("/{project_id}")
async def update_project(project_id: str, request: ProjectPatchRequest) -> Dict[str, Any]:
    service = get_workbench_workspace_service()
    try:
        project = service.update_project(project_id, name=request.name, project_type=request.project_type)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    logger.info("workbench project updated: %s", project_id)
    return {"status": "success", "data": project}


@router.delete("/{project_id}")
async def delete_project(project_id: str) -> Dict[str, Any]:
    service = get_workbench_workspace_service()
    deleted = service.delete_project(project_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="project not found")
    logger.info("workbench project deleted: %s", project_id)
    return {"status": "success", "data": True}
