"""
DawnChat - 本地 AI 服务和模型管理路由

职责：
1. 本地 AI 服务生命周期管理（initialize, shutdown, health_check）
2. 本地模型管理（list, download, delete）
3. 模型注册表查询
4. 下载任务管理
5. 模型生命周期状态查询
6. GPU 支持管理
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.llama_binary_manager import get_binary_manager
from app.services.model_lifecycle_manager import get_lifecycle_manager
from app.services.model_manager import get_model_manager
from app.utils.logger import api_logger as logger

# 创建路由器
router = APIRouter(prefix="/local-ai", tags=["Local AI"])


# ============ 请求/响应模型 ============

class DownloadModelRequest(BaseModel):
    """下载模型请求"""
    model_id: str


class GPUSupportRequest(BaseModel):
    """GPU 支持请求"""
    variant: str  # cuda-12, vulkan


# ============ 服务生命周期管理 ============

@router.get("/health")
async def health_check():
    """健康检查端点"""
    try:
        lifecycle = get_lifecycle_manager()
        status = lifecycle.get_status()
        
        is_healthy = status["state"] in ("loaded", "unloaded")
        
        return {
            "status": "ok" if is_healthy else "error",
            "llama_server": {
                "state": status["state"],
                "loaded_model": status["loaded_model"],
                "is_healthy": is_healthy,
            }
        }
    except Exception as e:
        logger.error(f"健康检查失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/initialize")
async def initialize_service():
    """
    初始化本地 AI 服务
    
    - 确保 llama-server 二进制可用
    - 不启动 llama-server（懒加载模式）
    """
    try:
        # 确保二进制部署
        binary_manager = get_binary_manager()
        binary_path = await binary_manager.ensure_binary()
        
        if not binary_path:
            raise HTTPException(
                status_code=500,
                detail="llama-server 二进制部署失败"
            )
        
        binary_info = binary_manager.get_binary_info()
        
        return {
            "status": "success",
            "message": "本地 AI 服务初始化成功（懒加载模式）",
            "binary": {
                "version": binary_info["version"],
                "variant": binary_info["variant"],
                "path": str(binary_path),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"初始化服务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/shutdown")
async def shutdown_service():
    """关闭本地 AI 服务（卸载模型）"""
    try:
        lifecycle = get_lifecycle_manager()
        success = await lifecycle.unload()
        
        if success:
            return {
                "status": "success",
                "message": "本地 AI 服务已关闭"
            }
        else:
            raise HTTPException(status_code=500, detail="关闭服务失败")
    except Exception as e:
        logger.error(f"关闭服务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status():
    """
    获取服务状态
    
    返回：
    - 生命周期状态 (unloaded, loading, loaded, unloading, error)
    - 当前加载的模型
    - 空闲时间和自动卸载倒计时
    - llama-server 进程信息
    """
    try:
        lifecycle = get_lifecycle_manager()
        status = lifecycle.get_status()
        
        return {
            "status": "success",
            "data": status
        }
    except Exception as e:
        logger.error(f"获取状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 模型注册表 ============

@router.get("/models/registry")
async def get_models_registry():
    """获取模型注册表（可下载的模型列表）"""
    try:
        manager = get_model_manager()
        registry = manager.get_registry()
        
        return {
            "status": "success",
            "data": registry
        }
    except Exception as e:
        logger.error(f"获取模型注册表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/registry/filter")
async def filter_models_registry(
    family: Optional[str] = None,
    provider: Optional[str] = None,
    tags: Optional[str] = None,
    max_size_gb: Optional[float] = None
):
    """筛选模型注册表"""
    try:
        manager = get_model_manager()
        
        tags_list = tags.split(',') if tags else None
        max_size_bytes = int(max_size_gb * 1024 * 1024 * 1024) if max_size_gb else None
        
        models = manager.filter_models(
            family=family,
            provider=provider,
            tags=tags_list,
            max_size=max_size_bytes
        )
        
        return {
            "status": "success",
            "count": len(models),
            "models": models
        }
    except Exception as e:
        logger.error(f"筛选模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 本地模型管理 ============

@router.get("/models")
async def list_installed_models():
    """
    列出已安装的本地模型
    
    扫描 models 目录下所有 GGUF 文件（递归），排除 .downloading 临时文件。
    
    返回字段：
    - id: 唯一标识（使用相对路径）
    - filename: 文件名
    - path: 绝对路径
    - size: 文件大小（字节）
    - size_display: 格式化大小
    - modified_at: 修改时间
    - author: 作者/来源
    - huggingface_id: HuggingFace 模型 ID（如果有）
    """
    try:
        manager = get_model_manager()
        models = manager.get_installed_models()
        
        # 添加更丰富的信息
        enriched_models = []
        for model in models:
            model_dict = {
                # 使用相对路径作为唯一 ID
                "id": model.get("id") or model["filename"],
                "name": model.get("name") or model["filename"].replace(".gguf", ""),
                "filename": model["filename"],
                "path": model["path"],
                "relative_path": model.get("relative_path"),
                "size": model["size"],
                "size_display": model["size_display"],
                "modified_at": model["modified_at"],
                "family": model.get("family"),
                "provider": model.get("provider"),
                # 新增字段
                "author": model.get("author"),
                "huggingface_id": model.get("huggingface_id"),
                "downloaded_at": model.get("downloaded_at"),
                "parameters": model.get("parameters"),
                "capabilities": model.get("capabilities"),
            }
            
            # 尝试从注册表获取额外信息
            registry_info = None
            if model.get("id"):
                registry_info = manager.get_model_info(model["id"])
            
            # 也尝试用文件名匹配
            if not registry_info:
                for m in manager.registry.get("models", []):
                    if m.get("local_filename") == model["filename"]:
                        registry_info = m
                        break
            
            if registry_info:
                model_dict.update({
                    "display_name": registry_info.get("name"),
                    "description": registry_info.get("description"),
                    "capabilities": registry_info.get("capabilities"),
                    "tags": registry_info.get("tags"),
                    "context_length": registry_info.get("context_length"),
                })
            
            enriched_models.append(model_dict)
        
        return {
            "status": "success",
            "count": len(enriched_models),
            "models": enriched_models
        }
    except Exception as e:
        logger.error(f"列出已安装模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/download")
async def download_model(request: DownloadModelRequest):
    """下载模型（从 HuggingFace，流式返回进度）"""
    try:
        manager = get_model_manager()
        
        # 检查模型信息
        model_info = manager.get_model_info(request.model_id)
        if not model_info:
            raise HTTPException(
                status_code=404,
                detail=f"未知的模型: {request.model_id}"
            )
        
        # 检查是否已安装
        if manager.is_model_installed(request.model_id):
            raise HTTPException(
                status_code=400,
                detail=f"模型 {request.model_id} 已安装"
            )
        
        async def generate_progress():
            """生成进度事件流"""
            import json
            
            try:
                logger.info(f"🚀 开始下载模型: {request.model_id}")
                
                async for progress in manager.download_model(request.model_id):
                    logger.debug(f"📦 下载进度: {progress}")
                    
                    # 检查取消请求
                    if manager.is_cancel_requested(request.model_id):
                        cancel_msg = {'status': 'cancelled', 'message': '下载已取消'}
                        logger.info(f"⛔ 下载已取消: {request.model_id}")
                        yield f"data: {json.dumps(cancel_msg)}\n\n"
                        return
                    
                    # 转换进度格式以兼容前端
                    sse_data = progress.copy()
                    
                    # 如果是下载中状态，添加 total 和 completed 字段（兼容前端）
                    if progress.get("status") == "downloading":
                        sse_data["total"] = progress.get("total_bytes", 0)
                        sse_data["completed"] = progress.get("downloaded_bytes", 0)
                    
                    yield f"data: {json.dumps(sse_data)}\n\n"
                
                logger.info(f"✅ 模型下载完成: {request.model_id}")
                
            except Exception as e:
                logger.error(f"❌ 下载模型过程中发生异常: {e}", exc_info=True)
                error_msg = {'status': 'error', 'message': str(e)}
                yield f"data: {json.dumps(error_msg)}\n\n"
        
        return StreamingResponse(
            generate_progress(),
            media_type="text/event-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/models/{model_id:path}")
async def delete_model(model_id: str):
    """
    删除本地模型
    
    支持两种 model_id 格式：
    1. 相对路径: lmstudio-community/gemma-3-1B-it-qat-GGUF_7e446ddb/gemma-3-1B-it-QAT-Q4_0.gguf
    2. 文件名: gemma-3-1B-it-QAT-Q4_0.gguf
    
    删除时会同时：
    - 删除模型文件
    - 清理空的父目录
    - 从 manifest.json 中移除记录
    """
    # URL 解码 model_id（因为路径中可能包含特殊字符）
    from urllib.parse import unquote
    model_id = unquote(model_id)
    
    logger.info(f"🗑️ 收到删除模型请求: {model_id}")
    
    try:
        manager = get_model_manager()
        lifecycle = get_lifecycle_manager()
        
        # 如果正在使用该模型，先卸载
        # 注意：需要检查模型文件名或完整路径
        current_model = lifecycle.current_model_id
        if current_model:
            # 检查是否匹配（可能是文件名或路径的一部分）
            if model_id in current_model or current_model in model_id:
                logger.info(f"模型 {model_id} 正在使用中，先卸载...")
                await lifecycle.unload()
        
        logger.info(f"🔄 开始删除模型: {model_id}")
        success = await manager.delete_model(model_id)
        
        if success:
            logger.info(f"✅ 模型删除成功: {model_id}")
            return {
                "status": "success",
                "message": f"模型 {model_id} 已删除"
            }
        else:
            logger.error(f"❌ 删除模型失败: {model_id}")
            raise HTTPException(
                status_code=404,
                detail=f"模型 {model_id} 不存在或删除失败"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 删除模型异常: {model_id}, 错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 下载任务管理 ============

@router.post("/models/cancel/{model_id}")
async def cancel_download(model_id: str):
    """取消模型下载"""
    try:
        manager = get_model_manager()
        
        success = manager.request_cancel(model_id)
        
        if success:
            return {
                "status": "success",
                "message": f"已请求取消模型 {model_id} 的下载"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail="无法取消下载（任务可能已完成或不存在）"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"取消下载失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/downloads")
async def get_download_tasks():
    """获取所有下载任务的状态"""
    try:
        manager = get_model_manager()
        tasks = manager.get_all_download_tasks()
        
        return {
            "status": "success",
            "count": len(tasks),
            "tasks": [manager.task_to_dict(task) for task in tasks]
        }
    except Exception as e:
        logger.error(f"获取下载任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/downloads/{model_id}")
async def get_download_status(model_id: str):
    """获取特定模型的下载状态"""
    try:
        manager = get_model_manager()
        task = manager.get_download_task(model_id)
        
        if task:
            return {
                "status": "success",
                "task": manager.task_to_dict(task)
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"未找到模型 {model_id} 的下载任务"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取下载状态失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 系统管理 ============

@router.get("/system/binary-info")
async def get_binary_info():
    """获取二进制信息"""
    try:
        binary_manager = get_binary_manager()
        info = binary_manager.get_binary_info()
        
        return {
            "status": "success",
            "data": info
        }
    except Exception as e:
        logger.error(f"获取二进制信息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/system/gpu-support")
async def enable_gpu_support(request: GPUSupportRequest):
    """下载 GPU 版本二进制（仅 Windows）"""
    try:
        binary_manager = get_binary_manager()
        
        if request.variant not in ("cuda-12", "vulkan"):
            raise HTTPException(
                status_code=400,
                detail=f"不支持的 GPU 变体: {request.variant}，支持: cuda-12, vulkan"
            )
        
        logger.info(f"开始下载 GPU 版本: {request.variant}")
        success = await binary_manager.download_gpu_binary(request.variant)
        
        if success:
            return {
                "status": "success",
                "message": f"GPU 版本 ({request.variant}) 安装成功"
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="GPU 版本下载失败（仅支持 Windows）"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用 GPU 支持失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 兼容旧 API（过渡期） ============

# 为了向后兼容，提供不带 /local-ai 前缀的别名路由
# 这些路由应在前端完全迁移后移除

@router.get("/models/installed", include_in_schema=False)
async def list_installed_models_compat():
    """[兼容] 列出已安装模型 - 重定向到新 API"""
    return await list_installed_models()

