"""
口语评分 API 路由

提供 Wav2Vec2 模型管理接口，用于 EchoFlow 插件的发音评分功能。
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.scoring_manager import get_scoring_manager
from app.utils.logger import get_logger

logger = get_logger("scoring_api")

router = APIRouter(prefix="/scoring", tags=["Scoring"])


# =============================================================================
# 请求模型
# =============================================================================

class DownloadRequest(BaseModel):
    """下载请求"""
    use_mirror: Optional[bool] = None


# =============================================================================
# 状态查询 API
# =============================================================================

@router.get("/status", response_model=dict)
async def get_status():
    """
    获取口语评分服务状态
    
    Returns:
        {
            "available": bool,         # 是否有可用模型
            "installed_models": list,  # 已安装的模型列表
            "default_model": str,      # 默认使用的模型
            "models_dir": str,         # 模型存储目录
        }
    """
    manager = get_scoring_manager()
    return manager.get_status()


@router.get("/models", response_model=dict)
async def list_models():
    """
    列出所有可用的 Wav2Vec2 模型及其安装状态
    
    Returns:
        {
            "models": [
                {
                    "id": "base",
                    "name": "Wav2Vec2 Base",
                    "hf_repo_id": "facebook/wav2vec2-base-960h",
                    "description": "基础模型...",
                    "size_mb": 380,
                    "installed": true,
                    "downloading": false,
                    "progress": 0,
                    "path": "/path/to/model" or null,
                },
                ...
            ]
        }
    """
    manager = get_scoring_manager()
    models = manager.list_models()
    return {"models": models}


# =============================================================================
# 下载管理 API
# =============================================================================

@router.post("/models/{model_id}/download")
async def download_model(
    model_id: str,
    request: DownloadRequest
):
    """
    启动模型下载（后台任务模式）
    
    Args:
        model_id: 模型标识 (base/large)
        request.use_mirror: 是否使用镜像加速
    
    Returns:
        {
            "status": "started" | "already_installed" | "already_downloading" | "error",
            "message": str,
            "task_id": str,
        }
    """
    manager = get_scoring_manager()
    
    # 检查是否已在下载
    if manager.is_download_active(model_id):
        return {
            "status": "already_downloading",
            "message": f"模型 {model_id} 正在下载中",
            "task_id": f"scoring_{model_id}",
        }
    
    try:
        result = await manager.download_model(
            model_size=model_id,
            use_mirror=request.use_mirror,
        )
        
        if result.get("status") == "already_installed":
            return {
                "status": "already_installed",
                "message": result.get("message"),
                "path": result.get("path"),
            }
        
        return {
            "status": "started",
            "message": f"模型 {model_id} 下载已启动",
            "task_id": result.get("task_id", f"scoring_{model_id}"),
            "use_mirror": request.use_mirror,
        }
        
    except Exception as e:
        logger.error(f"下载模型失败: {e}")
        raise HTTPException(500, str(e))


@router.get("/models/{model_id}/progress")
async def get_download_progress(model_id: str):
    """
    获取模型下载进度
    
    Args:
        model_id: 模型标识
    
    Returns:
        {
            "status": "pending" | "downloading" | "paused" | "completed" | "failed" | "cancelled" | "not_found",
            "progress": float,          # 0-100
            "downloaded_bytes": int,
            "total_bytes": int,
            "speed": str,               # "1.5 MB/s"
            "error_message": str | null,
        }
    """
    manager = get_scoring_manager()
    return manager.get_download_progress(model_id)


@router.post("/models/{model_id}/download/pause")
async def pause_download(model_id: str):
    """
    暂停模型下载
    
    Args:
        model_id: 模型标识
    
    Returns:
        {"status": "paused", "task_id": str}
    """
    manager = get_scoring_manager()
    
    if not manager.is_download_active(model_id):
        raise HTTPException(400, f"模型 {model_id} 没有正在进行的下载任务")
    
    result = await manager.request_pause(model_id)
    return result


@router.post("/models/{model_id}/download/cancel")
async def cancel_download(model_id: str):
    """
    取消模型下载
    
    Args:
        model_id: 模型标识
    
    Returns:
        {"status": "cancelled", "task_id": str}
    """
    manager = get_scoring_manager()
    result = await manager.request_cancel(model_id)
    return result


@router.post("/models/{model_id}/download/resume")
async def resume_download(
    model_id: str,
    request: DownloadRequest
):
    """
    恢复模型下载
    
    Args:
        model_id: 模型标识
        request.use_mirror: 是否使用镜像加速
    
    Returns:
        {"status": "started", "task_id": str}
    """
    manager = get_scoring_manager()
    
    result = await manager.download_model(
        model_size=model_id,
        use_mirror=request.use_mirror,
        resume=True,
    )
    
    return {
        "status": "started",
        "message": f"模型 {model_id} 下载已恢复",
        "task_id": result.get("task_id", f"scoring_{model_id}"),
    }


@router.get("/downloads/pending")
async def get_pending_downloads():
    """
    获取所有可恢复的下载任务（暂停或失败的）
    
    Returns:
        {
            "downloads": [
                {
                    "model_size": "base",
                    "hf_repo_id": "...",
                    "total_bytes": int,
                    "downloaded_bytes": int,
                    "progress": float,
                    "status": str,
                    "error_message": str | null,
                },
                ...
            ]
        }
    """
    manager = get_scoring_manager()
    downloads = manager.get_pending_downloads()
    return {"downloads": downloads}


# =============================================================================
# 模型管理 API
# =============================================================================

@router.get("/models/installed")
async def list_installed_models():
    """
    列出已安装的模型（包含本地路径）
    
    用于插件加载模型时使用本地路径而非从 HuggingFace 重新下载。
    
    Returns:
        {
            "models": [
                {
                    "id": "base",
                    "name": "Wav2Vec2 Base",
                    "path": "/path/to/model",
                    "hf_repo_id": "facebook/wav2vec2-base-960h",
                    "size_mb": 380
                },
                ...
            ],
            "default": "base",  # 推荐使用的模型
            "total": 1
        }
    """
    manager = get_scoring_manager()
    all_models = manager.list_models()
    
    installed = [m for m in all_models if m.get("installed")]
    
    # 默认模型优先级：base > large
    default_model = None
    for model_id in ["base", "large"]:
        if any(m["id"] == model_id for m in installed):
            default_model = model_id
            break
    
    return {
        "models": installed,
        "default": default_model,
        "total": len(installed)
    }


@router.delete("/models/{model_id}")
async def delete_model(model_id: str):
    """
    删除已安装的模型
    
    Args:
        model_id: 模型标识
    
    Returns:
        {"status": "deleted" | "not_found" | "error", "message": str}
    """
    manager = get_scoring_manager()
    result = await manager.delete_model(model_id)
    
    if result.get("status") == "error":
        raise HTTPException(500, result.get("message"))
    
    return result

