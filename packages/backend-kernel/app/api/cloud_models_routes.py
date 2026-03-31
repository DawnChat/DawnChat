"""
DawnChat - 云端模型配置管理路由

职责：
1. 管理云端AI厂商配置（API Key, Base URL）
2. 提供统一的模型列表（本地 + 云端）
3. 为 LiteLLM Provider 提供动态配置
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.storage import storage_manager
from app.utils.logger import api_logger as logger

# 创建路由器
router = APIRouter()


# ============ 请求/响应模型 ============

class ProviderConfigRequest(BaseModel):
    """厂商配置请求"""
    provider: str  # openai, anthropic, gemini, deepseek, qwen 等
    api_key: str
    base_url: Optional[str] = None  # 可选的自定义 Base URL


class ProviderConfigResponse(BaseModel):
    """厂商配置响应（不包含完整的 API Key）"""
    provider: str
    api_key_preview: str  # 只显示前几位和后几位
    base_url: Optional[str] = None
    is_configured: bool


# ============ 支持的厂商配置 ============

SUPPORTED_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "siliconflow": {
        "name": "SiliconFlow",
        "env_key": "SILICONFLOW_API_KEY",
        "default_base_url": "https://api.siliconflow.cn/v1",
        "openai_compatible": True,
        "models": [
            "deepseek-ai/DeepSeek-V3.2",
            "deepseek-ai/DeepSeek-R1",
            "Pro/zai-org/GLM-4.7",
            "zai-org/GLM-4.6V",
            "Qwen/Qwen3-VL-32B-Instruct",
            "Qwen/Qwen3-VL-235B-A22B-Instruct",
            "Qwen/Qwen3-VL-235B-A22B-Thinking"
        ]
    },
    "openai": {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "default_base_url": None,
        "openai_compatible": False,  # 原生支持
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1-preview",
            "o1-mini"
        ]
    },
    "gemini": {
        "name": "Google Gemini",
        "env_key": "GEMINI_API_KEY",
        "default_base_url": None,
        "openai_compatible": False,  # 原生支持
        "models": [
            "gemini-3-pro-preview",
            "gemini-3-flash-preview",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.0-flash-exp",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b"
        ]
    }
}


# ============ 工具函数 ============

def _mask_api_key(api_key: str) -> str:
    """遮蔽 API Key，只显示前4位和后4位"""
    if len(api_key) <= 8:
        return "***"
    return f"{api_key[:4]}...{api_key[-4:]}"


async def _check_provider_configs() -> None:
    """
    检查已配置的厂商
    
    注意：API Key 现在通过 LiteLLM Provider 动态获取，不再设置环境变量
    """
    try:
        configured_providers = []
        for provider in SUPPORTED_PROVIDERS.keys():
            api_key = await storage_manager.get_api_key(provider)
            if api_key:
                configured_providers.append(provider)
        
        if configured_providers:
            logger.info(f"已配置的云端厂商: {', '.join(configured_providers)}")
        else:
            logger.info("未配置任何云端厂商")
    except Exception as e:
        logger.warning(f"检查厂商配置失败: {e}")


async def fetch_provider_config(provider_id: str) -> Dict[str, Any]:
    """
    获取厂商配置（供 LiteLLM 调用使用）
    
    Returns:
        {
            "api_key": "xxx",
            "base_url": "https://...",  # 仅 OpenAI 兼容厂商有此字段
            "openai_compatible": True/False
        }
    """
    if provider_id not in SUPPORTED_PROVIDERS:
        raise ValueError(f"不支持的厂商: {provider_id}")
    
    config = SUPPORTED_PROVIDERS[provider_id]
    
    # 从存储读取 API Key
    api_key = await storage_manager.get_api_key(provider_id)
    if not api_key:
        raise ValueError(f"厂商 {provider_id} 未配置 API Key")
    
    result = {
        "api_key": api_key,
        "openai_compatible": config.get("openai_compatible", False)
    }
    
    # 如果是 OpenAI 兼容厂商，获取 Base URL
    if config.get("openai_compatible"):
        # 先尝试从 KV 存储读取用户自定义的 Base URL
        base_url = await storage_manager.get_app_config(f"provider.{provider_id}.base_url")
        if not base_url:
            # 使用默认 Base URL
            base_url = config.get("default_base_url")
        
        if base_url:
            result["base_url"] = base_url
    
    return result


# 为了向后兼容，保留别名
get_provider_config = fetch_provider_config


# ============ API 端点 ============

@router.get("/providers")
async def list_providers():
    """
    获取所有支持的厂商列表
    """
    try:
        providers_list = []
        
        for provider_id, config in SUPPORTED_PROVIDERS.items():
            # 检查是否已配置
            api_key = await storage_manager.get_api_key(provider_id)
            is_configured = bool(api_key)
            
            providers_list.append({
                "id": provider_id,
                "name": config["name"],
                "is_configured": is_configured,
                "model_count": len(config["models"])
            })
        
        return {
            "status": "success",
            "providers": providers_list
        }
    except Exception as e:
        logger.error(f"获取厂商列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/providers/{provider_id}")
async def get_provider_config_api(provider_id: str):
    """
    获取特定厂商的配置信息
    """
    try:
        if provider_id not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=404, detail=f"厂商 {provider_id} 不存在")
        
        config = SUPPORTED_PROVIDERS[provider_id]
        
        # 获取 API Key（遮蔽显示）
        api_key = await storage_manager.get_api_key(provider_id)
        base_url = await storage_manager.get_app_config(f"provider.{provider_id}.base_url")
        
        return {
            "status": "success",
            "provider": {
                "id": provider_id,
                "name": config["name"],
                "is_configured": bool(api_key),
                "api_key_preview": _mask_api_key(api_key) if api_key else None,
                "base_url": base_url or config.get("default_base_url"),
                "models": config["models"]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取厂商配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/providers/{provider_id}")
async def configure_provider(provider_id: str, request: ProviderConfigRequest):
    """
    配置厂商的 API Key 和 Base URL
    """
    try:
        if provider_id not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=404, detail=f"厂商 {provider_id} 不存在")
        
        # 验证 API Key 格式（基本检查）
        if not request.api_key or len(request.api_key) < 10:
            raise HTTPException(status_code=400, detail="API Key 格式无效")
        
        # 保存到安全存储
        await storage_manager.set_api_key(provider_id, request.api_key)
        logger.info(f"已保存 {provider_id} API Key")
        
        # 保存 Base URL（如果提供）
        if request.base_url:
            await storage_manager.set_app_config(f"provider.{provider_id}.base_url", request.base_url)
            logger.info(f"已保存 {provider_id} Base URL: {request.base_url}")
        
        return {
            "status": "success",
            "message": f"厂商 {provider_id} 配置成功",
            "provider": provider_id,
            "api_key_preview": _mask_api_key(request.api_key)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"配置厂商失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/providers/{provider_id}")
async def delete_provider_config(provider_id: str):
    """
    删除厂商配置
    """
    try:
        if provider_id not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=404, detail=f"厂商 {provider_id} 不存在")
        
        # 从安全存储删除 API Key
        await storage_manager.delete_api_key(provider_id)
        
        # 删除 Base URL 配置
        await storage_manager.set_app_config(f"provider.{provider_id}.base_url", None)
        
        # 删除已启用的模型配置
        await storage_manager.set_app_config(f"provider.{provider_id}.enabled_models", None)
        
        logger.info(f"已删除 {provider_id} 配置")
        
        return {
            "status": "success",
            "message": f"厂商 {provider_id} 配置已删除"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除厂商配置失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class EnabledModelsRequest(BaseModel):
    """启用的模型列表请求"""
    models: List[str]  # 模型 ID 列表，如 ["gpt-4o", "gpt-4o-mini"]


@router.get("/providers/{provider_id}/models")
async def get_provider_enabled_models(provider_id: str):
    """
    获取厂商已启用的模型列表
    """
    try:
        if provider_id not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=404, detail=f"厂商 {provider_id} 不存在")
        
        config = SUPPORTED_PROVIDERS[provider_id]
        
        # 获取用户启用的模型（如果未设置，默认全部启用）
        enabled_models = await storage_manager.get_app_config(f"provider.{provider_id}.enabled_models")
        if enabled_models is None:
            enabled_models = config["models"]  # 默认全部启用
        
        return {
            "status": "success",
            "provider_id": provider_id,
            "all_models": config["models"],
            "enabled_models": enabled_models
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取启用模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/providers/{provider_id}/models")
async def set_provider_enabled_models(provider_id: str, request: EnabledModelsRequest):
    """
    设置厂商启用的模型列表
    """
    try:
        if provider_id not in SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=404, detail=f"厂商 {provider_id} 不存在")
        
        config = SUPPORTED_PROVIDERS[provider_id]
        
        # 验证模型是否有效
        invalid_models = [m for m in request.models if m not in config["models"]]
        if invalid_models:
            raise HTTPException(status_code=400, detail=f"无效的模型: {invalid_models}")
        
        # 保存启用的模型列表
        await storage_manager.set_app_config(f"provider.{provider_id}.enabled_models", request.models)
        
        logger.info(f"已设置 {provider_id} 启用的模型: {request.models}")
        
        return {
            "status": "success",
            "message": f"已更新 {provider_id} 的模型配置",
            "enabled_models": request.models
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置启用模型失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/available")
async def list_available_models():
    """
    获取所有可用模型列表（本地 + 云端）
    
    返回格式：
    {
        "local": [...],  # 本地模型
        "cloud": {       # 云端模型（按厂商分组）
            "openai": [...],
            "gemini": [...]
        }
    }
    """
    from app.services.model_list_service import get_available_models
    
    try:
        return await get_available_models(caller="frontend")
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============ 启动时自动加载配置 ============

async def initialize_providers():
    """启动时检查已配置的厂商"""
    logger.info("正在加载云端模型厂商配置...")
    await _check_provider_configs()
    logger.info("云端模型厂商配置加载完成")
