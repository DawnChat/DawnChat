"""
Model List Service

提供统一的模型列表获取功能，被 SDK 和前端 API 共用。
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Config
from app.services.model_manager import get_model_manager
from app.storage import storage_manager

logger = logging.getLogger("dawnchat.model_list_service")

# 支持的云端厂商配置
SUPPORTED_PROVIDERS = {
    "siliconflow": {
        "name": "SiliconFlow",
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
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]
    },
    "gemini": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
    },
    "anthropic": {
        "name": "Anthropic",
        "models": ["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-haiku-20240307"]
    },
    "deepseek": {
        "name": "DeepSeek",
        "models": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"]
    },
    "qwen": {
        "name": "通义千问",
        "models": ["qwen-turbo", "qwen-plus", "qwen-max"]
    },
}


async def get_available_models(caller: Optional[str] = None) -> dict:
    """
    获取所有可用模型列表（本地 + 云端）
    
    Args:
        caller: 调用者标识，用于日志
    
    Returns:
        {
            "status": "success",
            "models": {
                "local": [...],
                "cloud": {
                    "openai": [...],
                    ...
                }
            },
            "total": {
                "local": N,
                "cloud": M
            }
        }
    """
    caller_info = f" (caller: {caller})" if caller else ""
    logger.debug(f"Getting available models{caller_info}")
    
    local_entries: List[Dict[str, Any]] = []
    cloud_entries: Dict[str, List[Dict[str, Any]]] = {}
    result: Dict[str, Any] = {
        "local": local_entries,
        "cloud": cloud_entries
    }
    
    # 1. 获取本地模型（GGUF）
    try:
        manager = get_model_manager()
        local_models = manager.get_installed_models()
        def detect_format(filename: str, model_format: Optional[str]) -> Optional[str]:
            if model_format:
                return model_format
            lower = filename.lower()
            if lower.endswith(".gguf"):
                return "gguf"
            if lower.endswith(".safetensors") or "mlx" in lower:
                return "mlx"
            return None

        mlx_dirs = set()
        for model in local_models:
            model_format = detect_format(model["filename"], model.get("format"))
            if model_format == "mlx":
                rel_path = model.get("relative_path") or model.get("path")
                if not rel_path:
                    continue
                dir_path = Path(rel_path).parent
                dir_key = dir_path.as_posix()
                if dir_key == ".":
                    dir_key = Path(rel_path).as_posix()
                if dir_key in mlx_dirs:
                    continue
                mlx_dirs.add(dir_key)
                base_path = Config.MODELS_DIR / dir_key
                size = 0
                if base_path.exists():
                    if base_path.is_file():
                        size = base_path.stat().st_size
                    else:
                        for f in base_path.rglob("*"):
                            if f.is_file():
                                size += f.stat().st_size
                local_entries.append({
                    "id": dir_key,
                    "model_key": f"local:{dir_key}",
                    "name": Path(dir_key).name,
                    "provider": "local",
                    "size": size,
                    "modified_at": model["modified_at"],
                    "parameters": model.get("parameters"),
                    "capabilities": model.get("capabilities", []),
                    "family": model.get("family"),
                    "format": model_format
                })
            else:
                local_entries.append({
                    "id": model["id"],
                    "model_key": f"local:{model['id']}",
                    "name": model.get("name") or model["filename"],
                    "provider": "local",
                    "size": model["size"],
                    "modified_at": model["modified_at"],
                    "parameters": model.get("parameters"),
                    "capabilities": model.get("capabilities", []),
                    "family": model.get("family"),
                    "format": model_format
                })
        result["local"] = local_entries
    except Exception as e:
        logger.warning(f"Failed to get local models: {e}")
    
    # 2. 获取云端模型（已配置的厂商 + 用户启用的模型）
    for provider_id, config in SUPPORTED_PROVIDERS.items():
        try:
            # 检查是否已配置 API Key
            api_key = await storage_manager.get_api_key(provider_id)
            if api_key:
                # 获取用户启用的模型
                enabled_models = await storage_manager.get_app_config(
                    f"provider.{provider_id}.enabled_models"
                )
                if enabled_models is None:
                    enabled_models = config["models"]  # 默认全部启用
                
                # 只返回启用的模型
                cloud_entries[provider_id] = [
                    {
                        "id": f"{provider_id}:{model}",
                        "model_key": f"{provider_id}:{model}",  # 统一格式：provider:model_name
                        "name": model,
                        "provider": provider_id,
                        "provider_name": config["name"]
                    }
                    for model in enabled_models
                ]
        except Exception as e:
            logger.warning(f"Failed to get cloud models for {provider_id}: {e}")
    
    total_local = len(result["local"])
    total_cloud = sum(len(models) for models in cloud_entries.values())
    
    logger.debug(f"Found {total_local} local + {total_cloud} cloud models{caller_info}")
    
    return {
        "status": "success",
        "models": result,
        "total": {
            "local": total_local,
            "cloud": total_cloud
        }
    }
