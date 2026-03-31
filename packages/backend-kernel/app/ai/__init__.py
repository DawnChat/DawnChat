"""AI 模块"""
from typing import Any

from app.ai.base import (
    AIProvider,
    CompletionRequest,
    CompletionResponse,
    HealthStatus,
    LocalModelManager,
    Message,
    ModelInfo,
    ServiceStatus,
)

try:
    from app.ai.litellm_provider import LiteLLMProvider as _LiteLLMProvider
except Exception:  # pragma: no cover - optional dependency for restricted test env
    LiteLLMProvider: Any = None
else:
    LiteLLMProvider = _LiteLLMProvider
from app.ai.mlx_provider import MLXProvider

__all__ = [
    "AIProvider",
    "LocalModelManager",
    "ServiceStatus",
    "Message",
    "CompletionRequest",
    "CompletionResponse",
    "ModelInfo",
    "HealthStatus",
    "LiteLLMProvider",
    "MLXProvider",
]
