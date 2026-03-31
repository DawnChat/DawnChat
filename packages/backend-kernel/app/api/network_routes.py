from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.network_service import NetworkService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/network", tags=["network"])

class ProxySettings(BaseModel):
    enabled: bool = False
    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None
    no_proxy: Optional[str] = "localhost,127.0.0.1"


class AutoProbeSettings(BaseModel):
    enabled: bool = True
    timeout_ms: int = 2500


class ProviderAccessSettings(BaseModel):
    mode: str = "auto"
    mirror_url: Optional[str] = None
    direct_url: Optional[str] = None
    mirror_prefix: Optional[str] = None
    mirror_host: Optional[str] = None
    direct_host: Optional[str] = None


class ResourceAccessSettings(BaseModel):
    global_mode: str = "auto"
    providers: Dict[str, ProviderAccessSettings] = {}
    auto_probe: AutoProbeSettings = AutoProbeSettings()
    updated_at: Optional[str] = None


@router.get("/proxy")
async def get_proxy_settings() -> ProxySettings:
    """获取代理设置"""
    try:
        settings = await NetworkService.get_proxy_settings()
        return ProxySettings(**settings)
    except Exception as e:
        logger.error(f"获取代理设置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/proxy")
async def save_proxy_settings(settings: ProxySettings):
    """保存并应用代理设置"""
    try:
        await NetworkService.save_proxy_settings(settings.model_dump())
        return {"message": "代理设置已保存", "restart_required": True}
    except Exception as e:
        logger.error(f"保存代理设置失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resource-access")
async def get_resource_access_settings() -> Dict[str, Any]:
    """获取资源访问策略设置"""
    try:
        settings = await NetworkService.get_resource_access_settings()
        return ResourceAccessSettings(**settings).model_dump()
    except Exception as e:
        logger.error(f"获取资源访问策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resource-access")
async def save_resource_access_settings(settings: ResourceAccessSettings):
    """保存资源访问策略设置"""
    try:
        saved = await NetworkService.save_resource_access_settings(settings.model_dump())
        return {
            "message": "资源访问策略已保存",
            "restart_required": True,
            "settings": saved,
        }
    except Exception as e:
        logger.error(f"保存资源访问策略失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/probe")
async def trigger_resource_probe() -> Dict[str, Any]:
    """手动触发资源连通性探测"""
    try:
        result = await NetworkService.probe_resource_access()
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"触发资源探测失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/probe/status")
async def get_probe_status() -> Dict[str, Any]:
    """获取最近一次资源连通性探测状态"""
    try:
        return await NetworkService.get_probe_status()
    except Exception as e:
        logger.error(f"获取探测状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
