from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from app.ai.base import CompletionRequest, Message
from app.config import Config
from app.utils.logger import get_logger

from .chunk import ModelChunkV1
from .litellm_provider_v3 import LiteLLMProviderV3
from .thinking import normalize_budget_tokens, normalize_effort

logger = get_logger("agentv3_gateway")


@dataclass(slots=True)
class GatewayRequest:
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = Config.TokenBudget.FINALIZE
    context_length: Optional[int] = Config.AGENTV3_CONTEXT_LENGTH
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[Any] = None
    thinking_enabled: bool = False
    thinking_effort: Optional[str] = None
    thinking_budget_tokens: Optional[int] = None


@dataclass(slots=True)
class GatewayCompletion:
    content: str
    tool_calls: List[Dict[str, Any]]
    usage: Dict[str, int]
    finish_reason: str


class AgentV3AIGateway:
    def __init__(self):
        self._provider = None
        self._provider_v3 = None
        try:
            from app.ai.litellm_provider import LiteLLMProvider

            self._provider = LiteLLMProvider()
            self._provider_v3 = LiteLLMProviderV3(self._provider)
        except Exception:
            # In restricted test environments LiteLLM may be unavailable.
            self._provider = None
            self._provider_v3 = None

    async def complete(self, request: GatewayRequest) -> GatewayCompletion:
        if self._provider is None:
            raise RuntimeError("litellm provider unavailable")
        logger.debug("gateway complete start model=%s", request.model or Config.DEFAULT_MODEL)
        completion_request = CompletionRequest(
            messages=request.messages,
            model=request.model or Config.DEFAULT_MODEL,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            context_length=request.context_length,
            tools=request.tools,
            tool_choice=request.tool_choice,
            provider_options=self._build_provider_options(request),
        )
        response = await self._provider.get_completion(completion_request)
        logger.debug("gateway complete finish model=%s", completion_request.model)
        return GatewayCompletion(
            content=response.content or "",
            tool_calls=response.tool_calls or [],
            usage=response.usage or {},
            finish_reason=response.finish_reason or "stop",
        )

    async def stream(self, request: GatewayRequest) -> AsyncIterator[ModelChunkV1]:
        if self._provider_v3 is None:
            yield ModelChunkV1(type="error", error="litellm provider unavailable")
            return
        logger.debug("gateway stream start model=%s", request.model or Config.DEFAULT_MODEL)
        completion_request = CompletionRequest(
            messages=request.messages,
            model=request.model or Config.DEFAULT_MODEL,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            context_length=request.context_length,
            tools=request.tools,
            tool_choice=request.tool_choice,
            stream=True,
            provider_options=self._build_provider_options(request),
        )
        try:
            async for piece in self._provider_v3.stream(completion_request):
                yield piece
        except Exception as err:
            logger.error("gateway stream error model=%s error=%s", completion_request.model, err, exc_info=True)
            yield ModelChunkV1(type="error", error=str(err))

    def _build_provider_options(self, request: GatewayRequest) -> Dict[str, Any]:
        effort = (request.thinking_effort or "").strip().lower()
        effort = normalize_effort(effort, default="medium")
        budget = normalize_budget_tokens(request.thinking_budget_tokens, default=0)
        return {
            "thinking_enabled": bool(request.thinking_enabled),
            "thinking_effort": effort,
            "thinking_budget_tokens": budget,
        }

