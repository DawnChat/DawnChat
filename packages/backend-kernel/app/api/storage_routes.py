"""
存储相关的 API 路由

提供配置管理、API 密钥管理等接口。
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..storage import storage_manager
from ..utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/storage", tags=["storage"])


# ==================== 请求/响应模型 ====================

class ConfigItem(BaseModel):
    """配置项"""
    key: str
    value: Any


class APIKeyCreate(BaseModel):
    """创建 API 密钥"""
    provider: str
    api_key: str


class APIKeyInfo(BaseModel):
    """API 密钥信息（不包含实际密钥）"""
    provider: str
    exists: bool


# ==================== 配置管理 ====================

@router.get("/config/{key}")
async def get_config(key: str, default: Optional[str] = None) -> Dict[str, Any]:
    """
    获取配置项
    
    Args:
        key: 配置键
        default: 默认值
        
    Returns:
        配置信息
    """
    try:
        value = await storage_manager.get_config(key, default)
        return {
            "key": key,
            "value": value,
            "exists": value is not None
        }
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config")
async def set_config(item: ConfigItem) -> Dict[str, str]:
    """
    设置配置项
    
    Args:
        item: 配置项
        
    Returns:
        成功消息
    """
    try:
        await storage_manager.set_config(item.key, item.value)
        return {"message": f"配置 '{item.key}' 已设置"}
    except Exception as e:
        logger.error(f"设置配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_all_configs() -> Dict[str, Any]:
    """
    获取所有配置
    
    Returns:
        所有配置
    """
    try:
        configs = await storage_manager.get_all_configs()
        return {"configs": configs}
    except Exception as e:
        logger.error(f"获取所有配置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== API 密钥管理 ====================

@router.post("/api-keys")
async def create_api_key(item: APIKeyCreate) -> Dict[str, str]:
    """
    设置 API 密钥
    
    Args:
        item: API 密钥信息
        
    Returns:
        成功消息
    """
    try:
        await storage_manager.set_api_key(item.provider, item.api_key)
        return {"message": f"API 密钥 '{item.provider}' 已设置"}
    except Exception as e:
        logger.error(f"设置 API 密钥失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api-keys/{provider}")
async def get_api_key_info(provider: str) -> APIKeyInfo:
    """
    获取 API 密钥信息（不返回实际密钥）
    
    Args:
        provider: 提供商名称
        
    Returns:
        API 密钥是否存在
    """
    try:
        api_key = await storage_manager.get_api_key(provider)
        return APIKeyInfo(
            provider=provider,
            exists=api_key is not None
        )
    except Exception as e:
        logger.error(f"获取 API 密钥信息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api-keys/{provider}")
async def delete_api_key(provider: str) -> Dict[str, str]:
    """
    删除 API 密钥
    
    Args:
        provider: 提供商名称
        
    Returns:
        成功消息
    """
    try:
        result = await storage_manager.delete_api_key(provider)
        if result:
            return {"message": f"API 密钥 '{provider}' 已删除"}
        else:
            raise HTTPException(status_code=404, detail=f"API 密钥 '{provider}' 不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 API 密钥失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 健康检查 ====================

@router.get("/health")
async def storage_health() -> Dict[str, Any]:
    """
    存储系统健康检查
    
    Returns:
        健康状态
    """
    try:
        # 测试各个存储是否正常
        test_key = "__health_check__"
        
        # 测试 KV 存储
        await storage_manager.set_config(test_key, "ok")
        kv_status = await storage_manager.get_config(test_key) == "ok"
        await storage_manager.config_storage.delete(test_key)
        
        # 测试安全存储
        secure_status = isinstance(storage_manager.secure_storage, 
                                   (storage_manager.secure_storage.__class__))
        
        # 测试数据库
        db_count = await storage_manager.user_storage.count()
        db_status = db_count >= 0
        
        return {
            "status": "healthy" if all([kv_status, secure_status, db_status]) else "unhealthy",
            "kv_storage": "ok" if kv_status else "error",
            "secure_storage": "ok" if secure_status else "error",
            "database": "ok" if db_status else "error",
            "user_count": db_count
        }
    except Exception as e:
        logger.error(f"存储健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

