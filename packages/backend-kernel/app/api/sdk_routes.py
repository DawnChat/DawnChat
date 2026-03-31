"""
DawnChat - SDK 路由

提供 Plugin SDK 调用 Host 能力的 API 端点。
这些端点供 dawnchat-sdk 包使用，Plugin 通过 HTTP 调用访问 Host 功能。

所有请求需要携带 X-Plugin-ID header 以标识来源 Plugin。

智能路由：
- 对于 execution_strategy=SYNC 的工具，直接执行并返回结果
- 对于 execution_strategy=ASYNC_QUEUE 的工具，提交到 TaskManager 并返回 task_id
  SDK 层会自动切换到 WebSocket 监听模式等待结果
"""

from pathlib import Path as FilePath
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Path
from pydantic import BaseModel, Field

from app.ai import CompletionRequest, LiteLLMProvider, Message
from app.config import Config
from app.plugin_ui_bridge import PluginUIBridgeError, get_plugin_ui_bridge_service
from app.services.github_download import (
    GitHubDownloadMeta,
    get_github_download_manager,
)
from app.services.hf_download_v2 import DownloadMeta, get_hf_download_manager_v2
from app.services.model_manager import get_model_manager
from app.storage import storage_manager
from app.utils.logger import get_logger

logger = get_logger("sdk_api")

router = APIRouter(prefix="/sdk", tags=["sdk"])


# ============ 请求/响应模型 ============

class SDKChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: Any  # 允许字符串、列表（多模态）或其他格式


class SDKChatRequest(BaseModel):
    """SDK AI 聊天请求"""
    messages: List[SDKChatMessage]
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    top_k: Optional[int] = None
    presence_penalty: Optional[float] = None
    frequency_penalty: Optional[float] = None
    stop: Optional[List[str]] = None
    context_length: Optional[int] = None


class SDKEmbeddingRequest(BaseModel):
    """SDK Embedding 请求"""
    text: str
    model: Optional[str] = None


class SDKDownloadStartRequest(BaseModel):
    source: str = Field(..., description="下载来源: huggingface/github/http")
    model_type: Optional[str] = Field(None, description="HF 下载模型类型")
    model_id: Optional[str] = Field(None, description="HF 下载模型 ID")
    hf_repo_id: Optional[str] = Field(None, description="HF 仓库 ID")
    save_dir: Optional[str] = Field(None, description="HF 保存目录")
    filename: Optional[str] = Field(None, description="HF 单文件名")
    url: Optional[str] = Field(None, description="URL 下载地址")
    save_path: Optional[str] = Field(None, description="URL 下载保存路径")
    task_id: Optional[str] = Field(None, description="URL 下载任务 ID")
    use_mirror: Optional[bool] = Field(None, description="是否使用镜像")
    resume: bool = Field(True, description="是否断点续传")


class SDKAgentContextPushItem(BaseModel):
    type: str = Field(..., description="context item type: text/image")
    text: Optional[str] = None
    uri: Optional[str] = None
    mime: Optional[str] = None


class SDKAgentContextPushRequest(BaseModel):
    plugin_id: Optional[str] = None
    mode: str = Field(default="append")
    items: List[SDKAgentContextPushItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


_sdk_download_task_index: Dict[str, Dict[str, Any]] = {}


# ============ 全局单例 ============

_litellm_provider = None


def get_ai_provider():
    """获取统一的 AI Provider（LiteLLM）"""
    global _litellm_provider
    if _litellm_provider is None:
        _litellm_provider = LiteLLMProvider()
    return _litellm_provider


def validate_plugin_id(x_plugin_id: Optional[str]) -> str:
    """验证 Plugin ID header"""
    if not x_plugin_id:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Plugin-ID header. SDK requests must identify the calling plugin."
        )
    return x_plugin_id


# ============ AI 端点 ============

@router.post("/ai/chat")
async def sdk_ai_chat(
    request: SDKChatRequest,
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    """
    SDK AI 聊天补全
    
    Plugin 通过此端点调用 Host 的 LLM 能力。
    """
    plugin_id = validate_plugin_id(x_plugin_id)
    logger.debug(f"[SDK] AI chat request: model={request.model}, messages_count={len(request.messages)}")
    logger.info(f"[SDK] Plugin '{plugin_id}' requesting AI chat")
    
    try:
        # 确定使用的模型
        model = request.model
        if not model:
            # 使用默认模型
            model = Config.DEFAULT_MODEL if hasattr(Config, 'DEFAULT_MODEL') else "default"
        
        # 使用 LiteLLM 进行 AI 调用
        provider = get_ai_provider()
        
        # 转换消息格式 (content 可能是 str, list, 或 None)
        messages = []
        for msg in request.messages:
            content = msg.content
            # 确保 content 是有效类型
            if content is None:
                content = ""
            elif not isinstance(content, (str, list)):
                content = str(content)
            messages.append(Message(role=msg.role, content=content))
        
        completion_request = CompletionRequest(
            messages=messages,
            model=model,
            temperature=request.temperature,
            max_tokens=request.max_tokens or Config.TokenBudget.MAX_LIMIT,
            stream=False,
            top_p=request.top_p,
            top_k=request.top_k,
            presence_penalty=request.presence_penalty,
            frequency_penalty=request.frequency_penalty,
            stop=request.stop,
            context_length=request.context_length
        )
        
        response = await provider.get_completion(completion_request)
        
        logger.info(f"[SDK] AI chat completed for plugin '{plugin_id}'")
        
        return {
            "status": "success",
            "content": response.content,
            "model": response.model,
            "finish_reason": response.finish_reason,
            "usage": response.usage
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        # LiteLLM 友好错误
        logger.error(f"[SDK] AI chat error for plugin '{plugin_id}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SDK] AI chat failed for plugin '{plugin_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ai/embedding")
async def sdk_ai_embedding(
    request: SDKEmbeddingRequest,
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    """
    SDK 文本向量化
    
    Plugin 通过此端点获取文本的向量表示。
    """
    plugin_id = validate_plugin_id(x_plugin_id)
    logger.info(f"[SDK] Plugin '{plugin_id}' requesting embedding")
    
    try:
        ai_provider = get_ai_provider()
        response, used_model = await ai_provider.get_embedding(request.text, model=request.model)
        
        # 获取第一个嵌入向量
        embedding = response.data[0]["embedding"] if response.data else []
        
        logger.info(f"[SDK] Embedding completed for plugin '{plugin_id}', dim={len(embedding)}")
        
        return {
            "status": "success",
            "embedding": embedding,
            "model": used_model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"[SDK] Embedding error for plugin '{plugin_id}': {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"[SDK] Embedding failed for plugin '{plugin_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agent/context/push")
async def sdk_agent_context_push(
    request: SDKAgentContextPushRequest,
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    plugin_id = str(request.plugin_id or validate_plugin_id(x_plugin_id)).strip()
    if not plugin_id:
        raise HTTPException(status_code=400, detail="plugin_id is required")
    payload = {
        "mode": str(request.mode or "append"),
        "items": [item.model_dump() for item in request.items],
        "metadata": dict(request.metadata or {}),
    }
    try:
        await get_plugin_ui_bridge_service().push_context(plugin_id, payload)
        return {"status": "success"}
    except PluginUIBridgeError as err:
        raise HTTPException(status_code=409, detail=err.message) from err
# ============ Downloads 端点（插件模型下载基础能力）============

def _remember_download_task(task_id: str, meta: Dict[str, Any]) -> None:
    if not task_id:
        return
    _sdk_download_task_index[task_id] = meta


def _load_task_meta(task_id: str) -> Optional[Dict[str, Any]]:
    indexed = _sdk_download_task_index.get(task_id)
    if indexed:
        return indexed

    meta_path = Config.DATA_DIR / f".{task_id}_download_meta.json"
    if not meta_path.exists():
        return None

    hf_meta = DownloadMeta.load(meta_path)
    if hf_meta and hf_meta.model_type and hf_meta.model_id:
        meta = {
            "backend": "hf",
            "task_id": task_id,
            "source": "huggingface",
            "model_type": hf_meta.model_type,
            "model_id": hf_meta.model_id,
        }
        _remember_download_task(task_id, meta)
        return meta

    gh_meta = GitHubDownloadMeta.load(meta_path)
    if gh_meta and gh_meta.task_id and gh_meta.original_url:
        meta = {
            "backend": "github",
            "task_id": gh_meta.task_id,
            "source": "github" if "github" in (gh_meta.original_url or "") else "http",
            "url": gh_meta.original_url,
        }
        _remember_download_task(task_id, meta)
        return meta
    return None


def _normalize_hf_task(task_id: str, progress: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "backend": "hf",
        "source": "huggingface",
        "status": progress.get("status", "unknown"),
        "progress": progress.get("progress", 0),
        "downloaded_bytes": progress.get("downloaded_bytes", 0),
        "total_bytes": progress.get("total_bytes", 0),
        "speed": progress.get("speed", ""),
        "error_message": progress.get("error_message"),
        "model_type": meta.get("model_type"),
        "model_id": meta.get("model_id"),
        "filename": progress.get("filename"),
        "hf_repo_id": meta.get("hf_repo_id"),
    }


def _normalize_github_task(task_id: str, progress: Dict[str, Any], meta: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "backend": "github",
        "source": meta.get("source", "github"),
        "status": progress.get("status", "unknown"),
        "progress": progress.get("progress", 0),
        "downloaded_bytes": progress.get("downloaded_bytes", 0),
        "total_bytes": progress.get("total_bytes", 0),
        "speed": progress.get("speed", ""),
        "error_message": progress.get("error_message"),
        "url": meta.get("url"),
        "save_path": meta.get("save_path"),
    }


@router.post("/downloads/start")
async def sdk_downloads_start(
    request: SDKDownloadStartRequest,
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID"),
):
    plugin_id = validate_plugin_id(x_plugin_id)
    source = str(request.source or "").strip().lower()
    logger.info("[SDK] Plugin '%s' starting download source=%s", plugin_id, source)

    if source == "huggingface":
        if not request.model_type or not request.model_id or not request.hf_repo_id or not request.save_dir:
            raise HTTPException(status_code=400, detail="huggingface requires model_type/model_id/hf_repo_id/save_dir")

        hf_manager = get_hf_download_manager_v2()
        save_dir = FilePath(request.save_dir).expanduser()
        start_result = await hf_manager.start_download(
            model_type=request.model_type,
            model_id=request.model_id,
            hf_repo_id=request.hf_repo_id,
            save_dir=save_dir,
            use_mirror=request.use_mirror,
            resume=request.resume,
            filename=request.filename,
        )
        task_id = str(start_result.get("task_id") or hf_manager._get_task_id(request.model_type, request.model_id))
        meta = {
            "backend": "hf",
            "task_id": task_id,
            "source": "huggingface",
            "model_type": request.model_type,
            "model_id": request.model_id,
            "hf_repo_id": request.hf_repo_id,
            "save_dir": str(save_dir),
        }
        _remember_download_task(task_id, meta)
        progress = hf_manager.get_progress(request.model_type, request.model_id)
        return {"status": "success", "task": _normalize_hf_task(task_id, progress, meta)}

    if source in {"github", "http"}:
        if not request.url or not request.save_path:
            raise HTTPException(status_code=400, detail="github/http requires url/save_path")

        gh_manager = get_github_download_manager()
        save_path = FilePath(request.save_path).expanduser()
        requested_task_id: Optional[str] = (request.task_id or "").strip() or None
        start_result = await gh_manager.start_download(
            url=request.url,
            save_path=save_path,
            task_id=requested_task_id,
            use_mirror=request.use_mirror if source == "github" else False,
            resume=request.resume,
        )
        resolved_task_id = str(start_result.get("task_id") or requested_task_id or "")
        meta = {
            "backend": "github",
            "task_id": resolved_task_id,
            "source": source,
            "url": request.url,
            "save_path": str(save_path),
        }
        _remember_download_task(resolved_task_id, meta)
        progress = gh_manager.get_progress(resolved_task_id)
        return {"status": "success", "task": _normalize_github_task(resolved_task_id, progress, meta)}

    raise HTTPException(status_code=400, detail=f"Unsupported source: {request.source}")


@router.get("/downloads/task/{task_id}")
async def sdk_downloads_get(
    task_id: str = Path(..., description="下载任务 ID"),
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID"),
):
    validate_plugin_id(x_plugin_id)
    meta = _load_task_meta(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Download task '{task_id}' not found")

    if meta["backend"] == "hf":
        hf_manager = get_hf_download_manager_v2()
        progress = hf_manager.get_progress(meta["model_type"], meta["model_id"])
        return {"status": "success", "task": _normalize_hf_task(task_id, progress, meta)}

    gh_manager = get_github_download_manager()
    progress = gh_manager.get_progress(task_id)
    return {"status": "success", "task": _normalize_github_task(task_id, progress, meta)}


@router.post("/downloads/task/{task_id}/pause")
async def sdk_downloads_pause(
    task_id: str = Path(..., description="下载任务 ID"),
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID"),
):
    validate_plugin_id(x_plugin_id)
    meta = _load_task_meta(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Download task '{task_id}' not found")

    if meta["backend"] == "hf":
        result = await get_hf_download_manager_v2().request_pause(meta["model_type"], meta["model_id"])
    else:
        result = await get_github_download_manager().request_pause(task_id)
    return {"status": "success", **result}


@router.post("/downloads/task/{task_id}/cancel")
async def sdk_downloads_cancel(
    task_id: str = Path(..., description="下载任务 ID"),
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID"),
):
    validate_plugin_id(x_plugin_id)
    meta = _load_task_meta(task_id)
    if not meta:
        raise HTTPException(status_code=404, detail=f"Download task '{task_id}' not found")

    if meta["backend"] == "hf":
        result = await get_hf_download_manager_v2().request_cancel(meta["model_type"], meta["model_id"])
    else:
        result = await get_github_download_manager().request_cancel(task_id)
    return {"status": "success", **result}


@router.get("/downloads/pending")
async def sdk_downloads_pending(
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID"),
):
    validate_plugin_id(x_plugin_id)

    tasks: List[Dict[str, Any]] = []
    hf_manager = get_hf_download_manager_v2()
    for item in hf_manager.get_pending_downloads():
        task_id = hf_manager._get_task_id(item["model_type"], item["model_id"])
        meta = {
            "backend": "hf",
            "task_id": task_id,
            "source": "huggingface",
            "model_type": item.get("model_type"),
            "model_id": item.get("model_id"),
            "hf_repo_id": item.get("hf_repo_id"),
            "save_dir": item.get("save_dir"),
        }
        _remember_download_task(task_id, meta)
        tasks.append(_normalize_hf_task(task_id, item, meta))

    gh_manager = get_github_download_manager()
    for meta_file in Config.DATA_DIR.glob(".*_download_meta.json"):
        gh_meta = GitHubDownloadMeta.load(meta_file)
        if not gh_meta or not gh_meta.task_id or not gh_meta.original_url:
            continue
        if gh_meta.status not in {"paused", "downloading", "failed"}:
            continue
        progress = gh_manager.get_progress(gh_meta.task_id)
        meta = {
            "backend": "github",
            "task_id": gh_meta.task_id,
            "source": "github" if "github" in gh_meta.original_url else "http",
            "url": gh_meta.original_url,
            "save_path": gh_meta.save_path,
        }
        _remember_download_task(gh_meta.task_id, meta)
        tasks.append(_normalize_github_task(gh_meta.task_id, progress, meta))

    return {"status": "success", "tasks": tasks, "total": len(tasks)}


# ============ Models 端点 ============

@router.get("/models/available")
async def sdk_models_available(
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    """
    SDK 获取可用模型列表
    
    返回所有可用的 AI 模型（本地 + 云端）。
    Plugin 通过此端点让用户选择使用哪个模型进行推理。
    """
    from app.services.model_list_service import get_available_models
    
    plugin_id = validate_plugin_id(x_plugin_id)
    logger.info(f"[SDK] Plugin '{plugin_id}' requesting available models")
    
    try:
        result = await get_available_models(caller=f"plugin:{plugin_id}")
        return result
    except Exception as e:
        logger.error(f"[SDK] List models failed for plugin '{plugin_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/local")
async def sdk_models_local(
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    """
    SDK 获取本地模型列表
    """
    plugin_id = validate_plugin_id(x_plugin_id)
    logger.info(f"[SDK] Plugin '{plugin_id}' requesting local models")
    
    try:
        manager = get_model_manager()
        local_models = manager.get_installed_models()
        
        models = [
            {
                "id": model["id"],
                "model_key": f"local:{model['id']}",  # 统一格式：provider:model_id
                "name": model.get("name") or model["filename"],
                "size": model["size"],
                "modified_at": model["modified_at"],
                "parameters": model.get("parameters"),
                "family": model.get("family")
            }
            for model in local_models
        ]
        
        logger.info(f"[SDK] Listed {len(models)} local models for plugin '{plugin_id}'")
        
        return {
            "status": "success",
            "models": models,
            "total": len(models)
        }
        
    except Exception as e:
        logger.error(f"[SDK] List local models failed for plugin '{plugin_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/cloud")
async def sdk_models_cloud(
    x_plugin_id: Optional[str] = Header(None, alias="X-Plugin-ID")
):
    """
    SDK 获取云端模型列表（按厂商分组）
    """
    from app.services.model_list_service import SUPPORTED_PROVIDERS
    
    plugin_id = validate_plugin_id(x_plugin_id)
    logger.info(f"[SDK] Plugin '{plugin_id}' requesting cloud models")
    
    try:
        result = {}
        
        for provider_id, config in SUPPORTED_PROVIDERS.items():
            try:
                api_key = await storage_manager.get_api_key(provider_id)
                if api_key:
                    enabled_models = await storage_manager.get_app_config(f"provider.{provider_id}.enabled_models")
                    if enabled_models is None:
                        enabled_models = config["models"]
                    
                    result[provider_id] = {
                        "name": config["name"],
                        "models": [
                            {
                                "id": f"{provider_id}:{model}",
                                "model_key": f"{provider_id}:{model}",  # 统一格式：provider:model_name
                                "name": model
                            }
                            for model in enabled_models
                        ]
                    }
            except Exception as e:
                logger.warning(f"[SDK] Failed to get cloud models for {provider_id}: {e}")
        
        total = sum(len(p["models"]) for p in result.values())
        logger.info(f"[SDK] Listed {total} cloud models for plugin '{plugin_id}'")
        
        return {
            "status": "success",
            "providers": result,
            "total": total
        }
        
    except Exception as e:
        logger.error(f"[SDK] List cloud models failed for plugin '{plugin_id}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
