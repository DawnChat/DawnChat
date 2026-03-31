"""
DawnChat Plugin System - API Routes

Provides REST API endpoints for plugin management.
"""

from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.plugins import get_plugin_manager
from app.plugins.installer_service import get_plugin_installer_service
from app.plugins.lifecycle_service import get_plugin_lifecycle_service
from app.plugins.plugin_log_service import PluginLogEntry, get_plugin_log_service
from app.plugins.versioning import parse_semver_tuple
from app.utils.logger import get_logger

logger = get_logger("plugins_routes")

router = APIRouter(prefix="/plugins", tags=["Plugins"])


class PluginActionResponse(BaseModel):
    """Response for plugin actions."""
    status: str
    message: str
    plugin_id: str
    port: Optional[int] = None


class PluginListResponse(BaseModel):
    """Response for plugin list."""
    status: str
    plugins: list[dict]
    count: int


class PluginInstallRequest(BaseModel):
    version: Optional[str] = None


class PluginInstallResponse(BaseModel):
    status: str
    message: str
    plugin_id: str
    version: Optional[str] = None


class TemplateEnsureRequest(BaseModel):
    template_id: str = "com.dawnchat.desktop-starter"
    force_refresh: bool = True


class CreatePluginFromTemplateRequest(BaseModel):
    template_id: str = "com.dawnchat.desktop-starter"
    app_type: str = "desktop"
    name: str
    plugin_id: str
    description: str = ""
    owner_email: str
    owner_user_id: str


class PluginPreviewResponse(BaseModel):
    status: str
    message: str
    plugin_id: str
    url: Optional[str] = None


class CreateDevSessionOperationRequest(BaseModel):
    template_id: str = "com.dawnchat.desktop-starter"
    app_type: str = "desktop"
    name: str
    plugin_id: str
    description: str = ""
    owner_email: str
    owner_user_id: str


class StartDevSessionOperationRequest(BaseModel):
    plugin_id: str


class RestartDevSessionOperationRequest(BaseModel):
    plugin_id: str


class StartRuntimeOperationRequest(BaseModel):
    plugin_id: str


class MobilePreviewShareUrlResponse(BaseModel):
    status: str
    plugin_id: str
    share_url: str
    lan_ip: str


class PluginLogIngestEntry(BaseModel):
    level: str = Field(..., min_length=1, max_length=16)
    message: str = Field(..., min_length=1, max_length=4000)
    data: Optional[Any] = None
    timestamp: Optional[str] = Field(default=None, max_length=64)


class PluginLogIngestRequest(BaseModel):
    mode: Literal["preview", "runtime"]
    source: Literal["frontend", "backend", "sdk"]
    request_id: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=96)
    metadata: dict[str, Any] = Field(default_factory=dict)
    logs: list[PluginLogIngestEntry] = Field(default_factory=list, max_length=200)


class IwpMarkdownFileReadResponse(BaseModel):
    status: str
    plugin_id: str
    iwp_root: str
    path: str
    content: str
    content_hash: str
    updated_at: str


class IwpMarkdownFileSaveRequest(BaseModel):
    path: str = Field(..., min_length=1)
    content: str
    expected_hash: str = ""


class IwpBuildStartRequest(BaseModel):
    reason: str = ""


SYSTEM_CONTEXT_FIELDS = {"plugin_id", "mode", "source", "session_id", "request_id"}


def _strip_system_context_fields(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    return {key: value for key, value in payload.items() if key not in SYSTEM_CONTEXT_FIELDS}


async def _get_initialized_manager():
    manager = get_plugin_manager()
    initialized = await manager.ensure_initialized()
    if not initialized:
        raise HTTPException(status_code=500, detail="Plugin manager initialization failed")
    return manager


@router.get("", response_model=PluginListResponse)
async def list_plugins():
    """
    List all installed plugins.
    
    Returns:
        List of plugins with their metadata and current state
    """
    manager = await _get_initialized_manager()
    plugins = manager.list_plugins()
    
    return PluginListResponse(
        status="success",
        plugins=plugins,
        count=len(plugins),
    )


@router.get("/market")
async def list_market_plugins(force_refresh: bool = False):
    manager = await _get_initialized_manager()
    plugins = await manager.list_market_plugins(force_refresh=force_refresh)
    return {
        "status": "success",
        "plugins": plugins,
        "count": len(plugins),
    }


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str):
    """
    Get detailed information about a specific plugin.
    
    Args:
        plugin_id: The plugin identifier
    
    Returns:
        Plugin details including manifest and runtime state
    """
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    
    return {
        "status": "success",
        "plugin": plugin,
        "detail_metadata": manager.get_plugin_detail_metadata(plugin_id),
    }


@router.post("/{plugin_id}/start", response_model=PluginActionResponse)
async def start_plugin(plugin_id: str):
    """
    Start a plugin.
    
    Creates the plugin's virtual environment (if needed),
    installs dependencies, and starts the plugin process.
    
    Args:
        plugin_id: The plugin identifier
    
    Returns:
        Action result including the port number if successful
    """
    manager = get_plugin_manager()
    
    # Check if plugin exists
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    if str(plugin.get("app_type") or "desktop") in {"web", "mobile"}:
        raise HTTPException(status_code=400, detail="Web/Mobile 应用目前仅支持开发预览模式")
    
    # Start the plugin
    port = await manager.start_plugin(plugin_id)
    
    if port:
        return PluginActionResponse(
            status="success",
            message=f"Plugin started on port {port}",
            plugin_id=plugin_id,
            port=port,
        )
    else:
        # Get updated plugin info for error message
        plugin = manager.get_plugin_snapshot(plugin_id)
        error_msg = plugin.get("error_message", "Unknown error") if plugin else "Unknown error"
        
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start plugin: {error_msg}",
        )


@router.post("/{plugin_id}/stop", response_model=PluginActionResponse)
async def stop_plugin(plugin_id: str):
    """
    Stop a running plugin.
    
    Sends SIGTERM to the plugin process and waits for graceful shutdown.
    
    Args:
        plugin_id: The plugin identifier
    
    Returns:
        Action result
    """
    manager = get_plugin_manager()
    
    # Check if plugin exists
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    
    # Stop the plugin
    success = await manager.stop_plugin(plugin_id)
    
    if success:
        return PluginActionResponse(
            status="success",
            message="Plugin stopped",
            plugin_id=plugin_id,
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to stop plugin",
        )


@router.post("/{plugin_id}/restart", response_model=PluginActionResponse)
async def restart_plugin(plugin_id: str):
    """
    Restart a plugin.
    
    Stops the plugin if running, then starts it again.
    
    Args:
        plugin_id: The plugin identifier
    
    Returns:
        Action result including the new port number
    """
    manager = get_plugin_manager()
    
    # Check if plugin exists
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    if str(plugin.get("app_type") or "desktop") in {"web", "mobile"}:
        raise HTTPException(status_code=400, detail="Web/Mobile 应用目前仅支持开发预览模式")
    
    # Restart the plugin
    port = await manager.restart_plugin(plugin_id)
    
    if port:
        return PluginActionResponse(
            status="success",
            message=f"Plugin restarted on port {port}",
            plugin_id=plugin_id,
            port=port,
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to restart plugin",
        )


@router.get("/{plugin_id}/status")
async def get_plugin_status(plugin_id: str):
    """
    Get the current status of a plugin.
    
    Args:
        plugin_id: The plugin identifier
    
    Returns:
        Current plugin state and runtime information
    """
    manager = get_plugin_manager()
    
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "state": plugin.get("state"),
        "runtime": plugin.get("runtime"),
        "error_message": plugin.get("error_message"),
    }


@router.post("/{plugin_id}/install", response_model=PluginInstallResponse)
async def install_plugin(plugin_id: str, request: PluginInstallRequest):
    manager = await _get_initialized_manager()
    market_items = await manager.list_market_plugins(force_refresh=True)
    candidates = [item for item in market_items if item.get("id") == plugin_id]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Plugin not found in market: {plugin_id}")

    requested_version = (request.version or "").strip()
    if requested_version:
        target = next((item for item in candidates if str(item.get("version") or "") == requested_version), None)
        if not target:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin version not found in market: {plugin_id}@{requested_version}",
            )
    else:
        target = max(candidates, key=lambda item: parse_semver_tuple(str(item.get("version") or "0.0.0")))

    package = target.get("package") or {}
    package_url = package.get("url")
    package_sha256 = package.get("sha256")
    version = str(target.get("version") or "")
    if not package_url:
        raise HTTPException(status_code=400, detail=f"Plugin package URL missing: {plugin_id}")

    await manager.install_from_package(
        plugin_id=plugin_id,
        version=version,
        package_url=package_url,
        package_sha256=package_sha256,
    )
    return PluginInstallResponse(
        status="accepted",
        message="Plugin install task submitted",
        plugin_id=plugin_id,
        version=version,
    )


@router.post("/template/ensure")
async def ensure_template_cache(request: TemplateEnsureRequest):
    manager = await _get_initialized_manager()
    payload = await manager.ensure_template_cached(
        request.template_id,
        force_refresh=request.force_refresh,
    )
    return {"status": "success", "data": payload}


@router.post("/create-from-template")
async def create_plugin_from_template(request: CreatePluginFromTemplateRequest):
    manager = await _get_initialized_manager()
    try:
        payload = await manager.create_plugin_from_template(
            template_id=request.template_id,
            app_name=request.name,
            app_description=request.description,
            desired_id=request.plugin_id,
            owner_email=request.owner_email,
            owner_user_id=request.owner_user_id,
            app_type=request.app_type,
        )
        return {"status": "success", "data": payload}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/operations/create-dev-session")
async def create_dev_session_operation(request: CreateDevSessionOperationRequest):
    service = get_plugin_lifecycle_service()
    task_id = await service.submit_create_dev_session(
        {
            "template_id": request.template_id,
            "app_type": request.app_type,
            "name": request.name,
            "plugin_id": request.plugin_id,
            "description": request.description,
            "owner_email": request.owner_email,
            "owner_user_id": request.owner_user_id,
        }
    )
    return {"status": "accepted", "task_id": task_id}


@router.post("/operations/start-dev-session")
async def start_dev_session_operation(request: StartDevSessionOperationRequest):
    manager = get_plugin_manager()
    plugin = manager.get_plugin_snapshot(request.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {request.plugin_id}")
    service = get_plugin_lifecycle_service()
    task_id = await service.submit_start_dev_session(request.plugin_id)
    return {"status": "accepted", "task_id": task_id}


@router.post("/operations/restart-dev-session")
async def restart_dev_session_operation(request: RestartDevSessionOperationRequest):
    manager = get_plugin_manager()
    plugin = manager.get_plugin_snapshot(request.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {request.plugin_id}")
    service = get_plugin_lifecycle_service()
    task_id = await service.submit_restart_dev_session(request.plugin_id)
    return {"status": "accepted", "task_id": task_id}


@router.post("/operations/start-runtime")
async def start_runtime_operation(request: StartRuntimeOperationRequest):
    manager = get_plugin_manager()
    plugin = manager.get_plugin_snapshot(request.plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {request.plugin_id}")
    if str(plugin.get("app_type") or "desktop") in {"web", "mobile"}:
        raise HTTPException(status_code=400, detail="Web/Mobile 应用目前仅支持开发预览模式")
    service = get_plugin_lifecycle_service()
    task_id = await service.submit_start_runtime(request.plugin_id)
    return {"status": "accepted", "task_id": task_id}


@router.get("/operations/{task_id}")
async def get_operation(task_id: str):
    service = get_plugin_lifecycle_service()
    payload = service.get_operation(task_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"Operation task not found: {task_id}")
    return {"status": "success", "data": payload}


@router.delete("/operations/{task_id}")
async def cancel_operation(task_id: str):
    service = get_plugin_lifecycle_service()
    success = await service.cancel_operation(task_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel operation '{task_id}'. It may not exist or already completed.",
        )
    return {"status": "success", "message": f"Operation '{task_id}' cancelled"}


@router.post("/{plugin_id}/update", response_model=PluginInstallResponse)
async def update_plugin(plugin_id: str):
    manager = await _get_initialized_manager()
    market_items = await manager.list_market_plugins(force_refresh=True)
    candidates = [item for item in market_items if item.get("id") == plugin_id]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"Plugin not found in market: {plugin_id}")
    target = max(candidates, key=lambda item: parse_semver_tuple(str(item.get("version") or "0.0.0")))

    latest_version = str(target.get("version") or "")
    if not latest_version:
        raise HTTPException(status_code=400, detail=f"Plugin version missing: {plugin_id}")
    if not manager.check_update(plugin_id, latest_version):
        raise HTTPException(status_code=400, detail=f"Plugin {plugin_id} is already up to date")

    package = target.get("package") or {}
    package_url = package.get("url")
    package_sha256 = package.get("sha256")
    if not package_url:
        raise HTTPException(status_code=400, detail=f"Plugin package URL missing: {plugin_id}")

    await manager.install_from_package(
        plugin_id=plugin_id,
        version=latest_version,
        package_url=package_url,
        package_sha256=package_sha256,
    )
    return PluginInstallResponse(
        status="accepted",
        message="Plugin update task submitted",
        plugin_id=plugin_id,
        version=latest_version,
    )


@router.get("/{plugin_id}/install/progress")
async def get_plugin_install_progress(plugin_id: str):
    manager = get_plugin_manager()
    installer = get_plugin_installer_service()
    progress = installer.get_progress(plugin_id)
    if progress.get("status") == "ready":
        await manager.refresh_registry()
    return {"status": "success", "progress": progress}


@router.post("/{plugin_id}/preview/start", response_model=PluginPreviewResponse)
async def start_plugin_preview(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    url = await manager.start_plugin_preview(plugin_id)
    if not url:
        status_payload = manager.get_plugin_preview_status(plugin_id) or {}
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start plugin preview: {status_payload.get('error_message') or 'unknown error'}",
        )
    return PluginPreviewResponse(
        status="success",
        message="Plugin preview started",
        plugin_id=plugin_id,
        url=url,
    )


@router.post("/{plugin_id}/preview/stop", response_model=PluginPreviewResponse)
async def stop_plugin_preview(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    ok = await manager.stop_plugin_preview(plugin_id)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to stop plugin preview: {plugin_id}")
    return PluginPreviewResponse(
        status="success",
        message="Plugin preview stopped",
        plugin_id=plugin_id,
        url=None,
    )


@router.get("/{plugin_id}/preview/status")
async def get_plugin_preview_status(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    preview = manager.get_plugin_preview_status(plugin_id)
    return {"status": "success", "plugin_id": plugin_id, "preview": preview}


@router.post("/{plugin_id}/preview/retry-install")
async def retry_plugin_preview_install(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    ok = await manager.retry_plugin_preview_install(plugin_id)
    if not ok:
        raise HTTPException(status_code=400, detail="当前预览会话无法重试安装")
    preview = manager.get_plugin_preview_status(plugin_id)
    return {"status": "success", "plugin_id": plugin_id, "preview": preview}


@router.get("/{plugin_id}/iwp/files")
async def list_plugin_iwp_files(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    try:
        payload = manager.list_iwp_markdown_files(plugin_id)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "iwp_root": payload.get("iwp_root") or "InstructWare.iw",
        "files": payload.get("files") or [],
    }


@router.get("/{plugin_id}/iwp/file", response_model=IwpMarkdownFileReadResponse)
async def read_plugin_iwp_file(plugin_id: str, path: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    try:
        list_payload = manager.list_iwp_markdown_files(plugin_id)
        file_payload = manager.read_iwp_markdown_file(plugin_id, path)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return IwpMarkdownFileReadResponse(
        status="success",
        plugin_id=plugin_id,
        iwp_root=str(list_payload.get("iwp_root") or "InstructWare.iw"),
        path=str(file_payload.get("path") or path),
        content=str(file_payload.get("content") or ""),
        content_hash=str(file_payload.get("content_hash") or ""),
        updated_at=str(file_payload.get("updated_at") or ""),
    )


@router.put("/{plugin_id}/iwp/file")
async def save_plugin_iwp_file(plugin_id: str, request: IwpMarkdownFileSaveRequest):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    try:
        payload = manager.save_iwp_markdown_file(
            plugin_id=plugin_id,
            relative_path=request.path,
            content=request.content,
            expected_hash=request.expected_hash,
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except RuntimeError as err:
        detail = str(err)
        if "modified externally" in detail:
            raise HTTPException(status_code=409, detail=detail) from err
        raise HTTPException(status_code=400, detail=detail) from err
    return {
        "status": "success",
        "plugin_id": plugin_id,
        "path": payload.get("path") or request.path,
        "content_hash": payload.get("content_hash") or "",
        "updated_at": payload.get("updated_at") or "",
    }


@router.post("/{plugin_id}/iwp/build")
async def start_plugin_iwp_build(plugin_id: str, request: IwpBuildStartRequest):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    del request
    try:
        task_id = await manager.start_iwp_build(plugin_id)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"status": "accepted", "plugin_id": plugin_id, "task_id": task_id}


@router.get("/{plugin_id}/iwp/build/{task_id}")
async def get_plugin_iwp_build_status(plugin_id: str, task_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    payload = await manager.get_iwp_build_task(task_id)
    if payload is None or str(payload.get("plugin_id") or "") != plugin_id:
        raise HTTPException(status_code=404, detail=f"IWP build task not found: {task_id}")
    return {"status": "success", "data": payload}


@router.get("/{plugin_id}/preview/mobile-share-url", response_model=MobilePreviewShareUrlResponse)
async def get_mobile_preview_share_url(plugin_id: str):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    try:
        payload = manager.get_mobile_preview_share_url(plugin_id)
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return MobilePreviewShareUrlResponse(
        status="success",
        plugin_id=plugin_id,
        share_url=payload["share_url"],
        lan_ip=payload["lan_ip"],
    )


@router.post("/{plugin_id}/logs/ingest")
async def ingest_plugin_logs(plugin_id: str, request: PluginLogIngestRequest):
    manager = await _get_initialized_manager()
    plugin = manager.get_plugin_snapshot(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin not found: {plugin_id}")
    if len(request.logs) > 200:
        raise HTTPException(status_code=400, detail="Too many log entries in one batch")
    metadata = _strip_system_context_fields(request.metadata)
    if isinstance(request.metadata, dict):
        dropped = sorted(set(request.metadata.keys()) & SYSTEM_CONTEXT_FIELDS)
        if dropped:
            logger.warning(
                "plugin log ingest dropped system context override: plugin=%s dropped=%s",
                plugin_id,
                ",".join(dropped),
            )
    entries = [
        PluginLogEntry(
            level=str(item.level or "INFO"),
            message=str(item.message or ""),
            timestamp=item.timestamp,
            data=_strip_system_context_fields(item.data),
        )
        for item in request.logs
        if str(item.message or "").strip()
    ]
    if not entries:
        return {"status": "success", "received": 0}
    received = get_plugin_log_service().append_entries(
        plugin_id,
        entries,
        mode=request.mode,
        source=request.source,
        request_id=str(request.request_id or ""),
        metadata=metadata,
        session_id=str(request.session_id or ""),
    )
    return {"status": "success", "received": received}


@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str):
    manager = await _get_initialized_manager()
    ok = await manager.uninstall_plugin_source(plugin_id)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to uninstall plugin: {plugin_id}")
    await manager.refresh_registry()
    return {"status": "success", "message": "Plugin source removed", "plugin_id": plugin_id}
