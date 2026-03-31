"""
LiteLLM Provider - 统一的多 AI 服务适配器

职责：提供统一的 AI 调用接口（completion）
不负责：模型下载、删除等管理操作（由 ModelManager 负责）

支持 100+ LLM API，包括：
- Local: llama.cpp (llama-server)
- Cloud: OpenAI, Anthropic, Google, Azure, AWS Bedrock
- Custom: OpenAI-compatible APIs

注意：本地模型使用懒加载机制，首次请求时自动加载。
"""

import asyncio
import importlib
import json
from typing import Any, AsyncIterator, Dict, Optional, Type, cast

import litellm
from litellm import acompletion, completion
from litellm.exceptions import (
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.config import Config
from app.services.model_manager import get_model_manager
from app.utils.json_utils import parse_llm_json

from ..utils.logger import get_logger
from .base import (
    AIProvider,
    CompletionRequest,
    CompletionResponse,
    Message,
    _strip_think_blocks,
    _strip_tool_calls_block,
    _ThinkStreamFilter,
)
from .mlx_provider import MLXProvider

logger = get_logger(__name__)

setattr(litellm, "suppress_debug_info", True)
setattr(litellm, "set_verbose", False)

_mlx_local_provider_cls: Optional[Type[Any]] = None
_mlx_local_provider_loaded = False


def _get_mlx_local_provider_cls() -> Optional[Type[Any]]:
    global _mlx_local_provider_cls, _mlx_local_provider_loaded
    if _mlx_local_provider_loaded:
        return _mlx_local_provider_cls
    _mlx_local_provider_loaded = True
    try:
        mod = importlib.import_module("app.ai.mlx_local_provider")
        candidate = getattr(mod, "MLXLocalProvider", None)
        if isinstance(candidate, type):
            _mlx_local_provider_cls = candidate
            return _mlx_local_provider_cls
    except Exception:
        _mlx_local_provider_cls = None
    return _mlx_local_provider_cls

class LiteLLMProvider(AIProvider):
    """
    基于 LiteLLM 的统一 AI Provider
    
    职责：
    - 提供统一的 AI 调用接口（支持流式和非流式）
    - 支持 100+ LLM APIs（本地 + 云端）
    - 自动重试和友好的错误处理
    - 本地模型懒加载（首次请求时自动加载）
    
    特点：
    - 本地模型使用 llama-server 的 OpenAI 兼容接口
    - 云端模型通过 API Key 访问
    
    不负责：
    - 模型管理（download, delete, list）由 ModelManager 负责
    """
    
    def __init__(self):
        self.local_base = None  # 动态获取 llama-server 端口
        self.log_truncate_limit = Config.LLM_LOG_TRUNCATE_LIMIT
        self._mlx_provider = MLXProvider()
        
        logger.info("LiteLLM Provider 已创建（本地模型使用懒加载）")
    
    def _safe_truncate(self, text: Any, limit: Optional[int] = None) -> str:
        """避免日志过长/包含不可序列化对象"""
        if limit is None:
            limit = self.log_truncate_limit
        try:
            s = json.dumps(text, ensure_ascii=False)
        except Exception:
            s = str(text)
        if limit and limit > 0 and len(s) > limit:
            return s[:limit] + "...(truncated)"
        return s
    
    @staticmethod
    def get_model_key(model_config: Optional[Dict[str, Any]]) -> str:
        """
        从 model_config 获取统一的 model_key
        
        统一格式：<provider>:<model_name>
        例如：local:lmstudio-community/.../xxx.gguf 或 openai:gpt-4o
        
        Args:
            model_config: 模型配置字典，可能包含：
                - model_key: 新格式，直接使用
                - provider + model: 旧格式，需要拼接
                
        Returns:
            统一格式的 model_key，如果无法解析则返回 "default"
        """
        if not model_config:
            return "default"
        
        # 优先使用 model_key（新格式）
        if model_key := model_config.get("model_key"):
            return model_key
        
        # 兼容旧格式：provider + model
        provider = model_config.get("provider", "local")
        model = model_config.get("model", "")
        if model:
            # 检查 model 是否已经包含 provider 前缀
            if ":" in model:
                return model
            return f"{provider}:{model}"
        
        return "default"
    
    def _normalize_tool_call(
        self,
        call: Any,
        ignore_if_no_name: bool = True,
        stringify_arguments: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        将模型返回的 tool_call 或内部传入的 tool_call 统一为 dict 结构。
        支持 dict / ChatCompletionMessageToolCall 等对象。
        """
        try:
            # 兼容字典与对象两种形式
            function_block = None
            if isinstance(call, dict):
                function_block = call.get("function", {})
                tool_id = call.get("id")
                tool_type = call.get("type", "function")
            else:
                function_block = getattr(call, "function", None)
                tool_id = getattr(call, "id", None)
                tool_type = getattr(call, "type", "function")
            
            # 提取 name
            name = None
            if isinstance(function_block, dict):
                name = function_block.get("name")
                arguments = function_block.get("arguments")
            else:
                name = getattr(function_block, "name", None)
                arguments = getattr(function_block, "arguments", None)
            
            if not name and ignore_if_no_name:
                logger.warning("忽略缺少名称的 tool_call: %s", self._safe_truncate(call, 400))
                return None
            
            # 解析参数
            parsed_args: Any = arguments
            if isinstance(arguments, str):
                try:
                    parsed_args = json.loads(arguments)
                except Exception:
                    parsed_args = arguments  # 保留原始字符串
            elif stringify_arguments:
                try:
                    parsed_args = json.dumps(arguments or {}, ensure_ascii=False)
                except Exception:
                    parsed_args = str(arguments)
            
            return {
                "id": tool_id,
                "type": tool_type or "function",
                "function": {
                    "name": name or "",
                    "arguments": parsed_args or {}
                }
            }
        except Exception as e:
            logger.warning("规范化 tool_call 失败: %s, error=%s", self._safe_truncate(call, 400), e)
            return None
    
    def _message_to_dict(self, msg: Message) -> Dict[str, Any]:
        """
        将内部 Message 转换为 LiteLLM 兼容的 dict，并过滤非法 tool_calls
        
        支持两种 content 格式：
        1. 纯文本: str
        2. 多模态内容: List[Dict] (OpenAI Vision API 标准格式)
        """
        data: Dict[str, Any] = {"role": msg.role}
        
        # 处理 content（支持纯文本和多模态格式）
        if msg.content is not None:
            if isinstance(msg.content, list):
                # 多模态格式：直接传递（LiteLLM 会原样转发给底层 API）
                data["content"] = msg.content
            else:
                # 纯文本格式
                data["content"] = msg.content
        else:
            # OpenAI 协议要求 content 至少为空字符串
            data["content"] = ""
        
        if msg.name:
            data["name"] = msg.name
        if msg.tool_call_id:
            data["tool_call_id"] = msg.tool_call_id
        if msg.tool_calls:
            cleaned_tool_calls = []
            for call in msg.tool_calls:
                normalized = self._normalize_tool_call(
                    call,
                    ignore_if_no_name=True,
                    stringify_arguments=True,  # 传给 LLM 需字符串
                )
                if normalized:
                    cleaned_tool_calls.append(normalized)
            if cleaned_tool_calls:
                data["tool_calls"] = cleaned_tool_calls
        return data
    
    def _extract_tool_calls_from_text(self, content: Any) -> Optional[list[Dict[str, Any]]]:
        if not content or not isinstance(content, str):
            logger.debug("工具调用解析跳过: content 为空或非字符串")
            return None
        def _normalize_calls(calls: Any) -> Optional[list[Dict[str, Any]]]:
            if isinstance(calls, dict):
                calls = [calls]
            if not isinstance(calls, list):
                return None
            normalized: list[Dict[str, Any]] = []
            for call in calls:
                normalized_call = self._normalize_tool_call(call, ignore_if_no_name=True)
                if normalized_call:
                    normalized.append(normalized_call)
            return normalized or None
        
        obj = parse_llm_json(content, logger=logger)
        if isinstance(obj, dict):
            calls = obj.get("tool_calls") or obj.get("tool_call")
            normalized = _normalize_calls(calls)
            if normalized:
                logger.debug("工具调用解析成功: 来自 parse_llm_json")
                return normalized
        
        key_variants = ["tool_calls", "tool_call", "'tool_calls'", "'tool_call'"]
        key_pos = -1
        for key in key_variants:
            key_pos = content.find(key)
            if key_pos >= 0:
                break
        if key_pos < 0:
            logger.debug("工具调用解析失败: 未找到 tool_calls 关键字")
            return None
        array_start = content.find("[", key_pos)
        if array_start < 0:
            logger.debug("工具调用解析失败: 未找到 tool_calls 数组起始")
            return None
        depth = 0
        in_string: Optional[str] = None
        escape = False
        end = None
        for i in range(array_start, len(content)):
            ch = content[i]
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch in ('"', "'"):
                if in_string == ch:
                    in_string = None
                elif not in_string:
                    in_string = ch
                continue
            if in_string:
                continue
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        snippet = content[array_start:end] if end else content[array_start:]
        wrapped = f'{{"tool_calls": {snippet}}}'
        logger.debug(
            "工具调用解析尝试: 使用包裹片段, key_pos=%s, array_start=%s, end=%s",
            key_pos,
            array_start,
            end,
        )
        obj = parse_llm_json(wrapped, logger=logger)
        if isinstance(obj, dict):
            calls = obj.get("tool_calls") or obj.get("tool_call")
            normalized = _normalize_calls(calls)
            if normalized:
                logger.debug("工具调用解析成功: 来自包裹片段")
            else:
                logger.debug("工具调用解析失败: 包裹片段无可用 tool_calls")
            return normalized
        return None
    
    async def _ensure_local_model_ready(self, model_id: str, max_retries: int = 3, retry_delay: float = 2.0) -> bool:
        """
        确保本地模型就绪（懒加载）
        
        增强健壮性：
        - 支持重试机制
        - 等待正在加载的模型
        - 更好的错误处理
        
        Args:
            model_id: 本地模型 ID
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            
        Returns:
            是否就绪
        """
        from app.services.model_lifecycle_manager import ModelState, get_lifecycle_manager
        
        for attempt in range(max_retries):
            try:
                lifecycle = get_lifecycle_manager()
                
                # 检查当前状态
                current_state = lifecycle.state
                
                # 如果模型正在加载中，等待加载完成
                if current_state == ModelState.LOADING:
                    logger.info(f"等待模型 {model_id} 加载完成... (尝试 {attempt + 1}/{max_retries})")
                    # 等待加载完成（最多等待 120 秒）
                    wait_success = await lifecycle._wait_for_loading()
                    if wait_success:
                        self.local_base = lifecycle.get_api_base()
                        logger.info(f"本地模型 {model_id} 就绪，API: {self.local_base}")
                        return True
                    else:
                        logger.warning("等待模型加载超时，将重试...")
                        await asyncio.sleep(retry_delay)
                        continue
                
                # 如果模型处于错误状态，等待一段时间后重试
                if current_state == ModelState.ERROR:
                    logger.warning(f"模型处于错误状态，等待 {retry_delay}s 后重试... (尝试 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                    # 清除错误状态，尝试重新加载
                    lifecycle._state = ModelState.UNLOADED
                    lifecycle._error_message = None
                
                # 尝试确保模型就绪
                success = await lifecycle.ensure_model_ready(model_id)
                
                if success:
                    # 更新本地服务端点
                    self.local_base = lifecycle.get_api_base()
                    logger.info(f"本地模型 {model_id} 就绪，API: {self.local_base}")
                    return True
                else:
                    if attempt < max_retries - 1:
                        logger.warning(f"本地模型 {model_id} 加载失败，{retry_delay}s 后重试... (尝试 {attempt + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.error(f"本地模型 {model_id} 加载失败，已达到最大重试次数")
                        
            except Exception as e:
                logger.error(f"确保本地模型就绪时发生异常: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    logger.warning(f"将在 {retry_delay}s 后重试... (尝试 {attempt + 1}/{max_retries})")
                    await asyncio.sleep(retry_delay)
                else:
                    return False
        
        return False
    
    def parse_model_name(self, model_str: str) -> tuple[str, str]:
        """
        解析模型名称
        
        格式: <provider>:<model_name>
        
        Args:
            model_str: 模型字符串（如 "local:llama3.2", "openai:gpt-4"）
            
        Returns:
            (provider, model_name) 元组
        """
        if ":" in model_str:
            provider, model_name = model_str.split(":", 1)
            provider = provider.strip()
            model_name = model_name.strip()
            
            # 兼容前端/存储已包含 provider 前缀的情况，避免出现 gemini:gemini:xxx
            duplicate_prefix = f"{provider}:"
            if model_name.startswith(duplicate_prefix):
                model_name = model_name[len(duplicate_prefix):]
            
            return provider, model_name
        
        # 无前缀时默认使用本地模型
        return "local", model_str
    
    def _detect_local_model_format(self, model_id: str) -> Optional[str]:
        try:
            manager = get_model_manager()
            path = manager.get_model_path(model_id)
            if not path:
                return None
            if path.is_dir():
                for p in path.rglob("*.safetensors"):
                    if p.is_file():
                        return "mlx"
                for p in path.rglob("*.gguf"):
                    if p.is_file():
                        return "gguf"
                return None
            lower = str(path).lower()
            if lower.endswith(".gguf"):
                return "gguf"
            if lower.endswith(".safetensors") or "mlx" in lower:
                return "mlx"
            return None
        except Exception:
            return None
    
    def build_litellm_model(self, provider: str, model_name: str) -> str:
        """
        构建 LiteLLM 模型标识
        
        Args:
            provider: 提供商（local, openai, anthropic, deepseek, qwen等）
            model_name: 模型名称
            
        Returns:
            LiteLLM 格式的模型名称
        """
        provider_mapping = {
            "local": "openai",  # llama-server 使用 OpenAI 兼容接口
            "openai": "openai",
            "anthropic": "anthropic",
            "azure": "azure",
            "gemini": "gemini",
            "claude": "anthropic",
            "gpt": "openai",
            # OpenAI 兼容的厂商统一使用 "openai" 前缀
            "deepseek": "openai",
            "qwen": "openai",
            "moonshot": "openai",
            "zhipu": "openai",
            "siliconflow": "openai"
        }
        
        litellm_provider = provider_mapping.get(provider.lower(), provider)
        
        # 本地模型使用 OpenAI 兼容接口（llama-server）
        # 直接返回 openai/{model_name}，api_base 会指向 llama-server
        return f"{litellm_provider}/{model_name}"
    
    async def get_provider_config_for_call(self, provider: str) -> Optional[Dict[str, str]]:
        """
        获取厂商的调用配置
        
        所有云端厂商都需要从存储中获取 API Key，以确保用户配置的 Key 能正确使用。
        
        Args:
            provider: 厂商名称
            
        Returns:
            配置字典 {"api_key": "xxx", "api_base": "https://..."}
            如果是本地模型，返回 None
        """
        # 本地模型不需要额外配置
        if provider == "local":
            return None
        
        try:
            from app.api.cloud_models_routes import fetch_provider_config
            config = await fetch_provider_config(provider)
            
            result = {"api_key": config["api_key"]}
            
            # OpenAI 兼容的厂商需要额外的 base_url
            if config.get("openai_compatible") and config.get("base_url"):
                result["api_base"] = config["base_url"]
            
            return result
        except Exception as e:
            logger.warning(f"获取 {provider} 配置失败: {e}")
            return None
    
    async def _get_default_model(self) -> str:
        """获取默认模型"""
        try:
            # 1. 尝试从用户偏好获取
            from app.storage import storage_manager
            # 尝试获取用户选择的模型
            preferred_model = await storage_manager.get_config("user_preference:model")
            logger.info(f"尝试从用户偏好获取模型: {preferred_model}")
            if preferred_model:
                 return preferred_model
                 
            # 2. 自动选择最佳本地模型
            from app.services.model_manager import get_model_manager
            manager = get_model_manager()
            installed_models = manager.get_installed_models()
            
            if not installed_models:
                logger.warning("未找到已安装的模型，回退到 openai:gpt-3.5-turbo")
                return "openai:gpt-3.5-turbo"
                
            # 策略: 优先 Vision, 其次 < 10B
            candidates = []
            for m in installed_models:
                # 简单的参数量判断逻辑
                params = str(m.get("parameters", "")).upper()
                size_bytes = m.get("size", 0)
                is_small = False
                
                if "B" in params:
                    try:
                        val = float(params.replace("B", ""))
                        if val < 10:
                            is_small = True
                    except Exception:
                        pass
                elif size_bytes > 0:
                     # 如果只有文件大小，假设 < 10GB 为小模型 (粗略估计)
                     if size_bytes < 10 * 1024 * 1024 * 1024:
                         is_small = True
                else:
                    # 无法判断，默认认为是小模型
                    is_small = True
                
                m["_is_small"] = is_small
                candidates.append(m)
            
            # 1. Vision & Small
            vision_small = [m for m in candidates if "vision" in m.get("capabilities", []) and m["_is_small"]]
            if vision_small:
                return vision_small[0]["id"]
            
            # 2. Vision (any size)
            vision_any = [m for m in candidates if "vision" in m.get("capabilities", [])]
            if vision_any:
                return vision_any[0]["id"]
            
            # 3. Small (any capability)
            small_any = [m for m in candidates if m["_is_small"]]
            if small_any:
                return small_any[0]["id"]
            
            # 4. Any
            return candidates[0]["id"]
            
        except Exception as e:
            logger.error(f"获取默认模型失败: {e}", exc_info=True)
            return "openai:gpt-3.5-turbo"

    def _is_embedding_model_entry(self, model: Dict[str, Any]) -> bool:
        candidates = [
            model.get("name"),
            model.get("filename"),
            model.get("id"),
            model.get("relative_path"),
            model.get("huggingface_id"),
        ]
        for value in candidates:
            if value and "embedding" in str(value).lower():
                return True
        return False

    def _is_preferred_embedding_model(self, model: Dict[str, Any]) -> bool:
        candidates = [
            model.get("name"),
            model.get("filename"),
            model.get("id"),
            model.get("relative_path"),
            model.get("huggingface_id"),
        ]
        for value in candidates:
            if value and "qwen3-embedding-0.6b" in str(value).lower():
                return True
        return False

    async def _get_default_embedding_model(self) -> str:
        try:
            from app.storage import storage_manager

            preferred = await storage_manager.get_config("user_preference:embedding_model")
            if preferred:
                return preferred
        except Exception:
            pass

        manager = get_model_manager()
        installed_models = manager.get_installed_models()
        embedding_models = [m for m in installed_models if self._is_embedding_model_entry(m)]
        if not embedding_models:
            raise ValueError("未找到已安装的本地 embedding 模型")
        for model in embedding_models:
            if self._is_preferred_embedding_model(model):
                return model["id"]
        return embedding_models[0]["id"]

    async def get_embedding(self, input_data: Any, model: Optional[str] = None) -> tuple[Any, str]:
        provider = "unknown"
        try:
            if not model or model == "default":
                model = await self._get_default_embedding_model()
                logger.info(f"使用默认 embedding 模型: {model}")

            provider, model_name = self.parse_model_name(model)
            model = f"{provider}:{model_name}"
            litellm_model = self.build_litellm_model(provider, model_name)

            local_format = None
            if provider == "local":
                local_format = self._detect_local_model_format(model_name)
                if local_format == "mlx":
                    raise ValueError("本地 MLX 模型暂不支持 embedding")
                if not await self._ensure_local_model_ready(model_name):
                    raise ValueError(f"本地模型 {model_name} 加载失败")

            provider_config = await self.get_provider_config_for_call(provider)

            def sync_embedding():
                params = {
                    "model": litellm_model,
                    "input": input_data,
                    "encoding_format": "float",
                }
                if provider == "local":
                    params["api_base"] = self.local_base
                    params["api_key"] = "not-needed"
                elif provider_config:
                    params["api_key"] = provider_config["api_key"]
                    if "api_base" in provider_config:
                        params["api_base"] = provider_config["api_base"]
                return cast(Any, litellm).embedding(**params)

            response = await asyncio.to_thread(sync_embedding)
            return response, model

        except AuthenticationError as e:
            error_msg = f"❌ 认证失败 ({provider}): API Key 无效或未配置"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)

        except RateLimitError as e:
            error_msg = f"❌ 请求过于频繁 ({provider}): 已达到速率限制"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)

        except BadRequestError as e:
            error_msg = f"❌ 请求参数错误: {str(e)}"
            logger.error(f"{error_msg}")
            raise ValueError(error_msg)

        except ServiceUnavailableError as e:
            error_msg = f"❌ 服务不可用 ({provider}): {str(e)}"
            logger.error(f"{error_msg}")
            raise ValueError(error_msg)

        except Timeout as e:
            error_msg = f"❌ 请求超时 ({provider}): 服务响应时间过长"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)

        except Exception as e:
            error_msg = f"❌ Embedding 请求失败: {str(e)}"
            logger.error(f"{error_msg}", exc_info=True)
            raise ValueError(error_msg)

    async def get_completion(self, request: CompletionRequest) -> CompletionResponse:
        """获取 AI 补全（非流式）"""
        provider = "unknown"
        try:
            # 处理默认模型
            if not request.model or request.model == "default":
                request.model = await self._get_default_model()
                logger.info(f"使用默认模型: {request.model}")

            # 解析模型名称
            provider, model_name = self.parse_model_name(request.model)
            # 规范化请求中的模型，避免重复前缀
            request.model = f"{provider}:{model_name}"
            litellm_model = self.build_litellm_model(provider, model_name)
            
            logger.info(f"请求补全: {request.model} -> {litellm_model}")
            
            local_format = None
            if provider == "local":
                local_format = self._detect_local_model_format(model_name)
                if local_format == "gguf" or local_format is None:
                    if not await self._ensure_local_model_ready(model_name):
                        raise ValueError(f"本地模型 {model_name} 加载失败")
                elif local_format == "mlx":
                    pass
            
            # 获取厂商配置（OpenAI 兼容厂商需要动态传递配置）
            provider_config = await self.get_provider_config_for_call(provider)
            
            messages = [self._message_to_dict(msg) for msg in request.messages]
            logger.debug(
                "LiteLLM 请求参数: model=%s, temperature=%s, max_tokens=%s, tools=%s, tools_payload=%s, messages=%s",
                litellm_model,
                request.temperature,
                request.max_tokens,
                [t.get("function", {}).get("name") for t in (request.tools or [])],
                self._safe_truncate(request.tools),
                self._safe_truncate(messages),
            )
            
            
            mlx_target = None
            if provider == "local" and local_format == "mlx":
                mlx_target = await self._mlx_provider.resolve_target(model_name)
                if mlx_target.mode == "inprocess":
                    mlx_local_provider_cls = _get_mlx_local_provider_cls()
                    if mlx_local_provider_cls is None:
                        raise ValueError("未安装 MLX 运行时，无法使用本地 MLX 模型")
                    mlx = mlx_local_provider_cls()
                    content, finish_reason, usage, tool_calls = await mlx.generate_completion(request=request)
                    logger.debug("MLX 模型原始响应: %s", content)
                    logger.debug("MLX 模型原始 tool_calls: %s", self._safe_truncate(tool_calls))
                    content = _strip_think_blocks(content or "")
                    if not tool_calls:
                        tool_calls = self._extract_tool_calls_from_text(content)
                    if tool_calls:
                        content = _strip_tool_calls_block(content)
                    logger.debug("MLX 模型解析后 tool_calls: %s", self._safe_truncate(tool_calls))
                    logger.debug(
                        "MLX 模型响应: content=%s, finish_reason=%s, usage=%s, tool_calls=%s",
                        content,
                        finish_reason,
                        usage,
                        tool_calls,
                    )
                    return CompletionResponse(
                        content=content,
                        model=request.model,
                        finish_reason=finish_reason,
                        usage=usage,
                        tool_calls=tool_calls,
                    )

            def sync_completion():
                model_for_call = litellm_model
                params: Dict[str, Any] = {
                    "model": litellm_model,
                    "messages": messages,
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                }
                if request.tools:
                    params["tools"] = request.tools
                if request.tool_choice is not None:
                    params["tool_choice"] = request.tool_choice
                if request.top_p is not None:
                    params["top_p"] = request.top_p
                if request.presence_penalty is not None:
                    params["presence_penalty"] = request.presence_penalty
                if request.frequency_penalty is not None:
                    params["frequency_penalty"] = request.frequency_penalty
                if request.stop is not None:
                    params["stop"] = request.stop
                if request.top_k is not None:
                    params["top_k"] = request.top_k
                if provider == "local":
                    if mlx_target and mlx_target.mode == "http":
                        model_for_call = mlx_target.litellm_model or model_for_call
                        params["model"] = model_for_call
                        params["api_base"] = mlx_target.api_base
                        params["api_key"] = "not-needed"
                    else:
                        params["api_base"] = self.local_base
                        params["api_key"] = "not-needed"
                elif provider_config:
                    params["api_key"] = provider_config["api_key"]
                    if "api_base" in provider_config:
                        params["api_base"] = provider_config["api_base"]
                return cast(Any, completion)(**params)

            response = await asyncio.to_thread(sync_completion)
            response_any = cast(Any, response)
            
            # 提取响应
            choices = getattr(response_any, "choices", None) or []
            if not choices:
                logger.warning("LiteLLM 响应不包含任何选项 (choices)")
                return CompletionResponse(
                    content="",
                    model=request.model,
                    finish_reason="empty_response",
                    usage={},
                    tool_calls=None
                )

            choice = choices[0]
            message = getattr(choice, "message", None)
            content = getattr(message, "content", None) or ""
            finish_reason = getattr(choice, "finish_reason", "")
            
            raw_tool_calls = getattr(message, "tool_calls", None)
            tool_calls = None
            if raw_tool_calls:
                tool_calls = []
                for call in raw_tool_calls:
                    normalized = self._normalize_tool_call(call, ignore_if_no_name=True)
                    if normalized:
                        tool_calls.append(normalized)
            content = _strip_think_blocks(content or "")
            if not tool_calls:
                tool_calls = self._extract_tool_calls_from_text(content)
            if tool_calls:
                content = _strip_tool_calls_block(content)
            logger.debug(
                "LiteLLM 响应: finish_reason=%s, content=%s, tool_calls=%s",
                finish_reason,
                self._safe_truncate(content, 6000),
                self._safe_truncate(tool_calls),
            )
            
            usage_obj = getattr(response_any, "usage", None)
            usage = {
                "prompt_tokens": getattr(usage_obj, "prompt_tokens", 0) or 0,
                "completion_tokens": getattr(usage_obj, "completion_tokens", 0) or 0,
                "total_tokens": getattr(usage_obj, "total_tokens", 0) or 0,
            }
            
            return CompletionResponse(
                content=content,
                model=request.model,
                finish_reason=finish_reason,
                usage=usage,
                tool_calls=tool_calls
            )
            
        except AuthenticationError as e:
            error_msg = f"❌ 认证失败 ({provider}): API Key 无效或未配置"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)
            
        except RateLimitError as e:
            error_msg = f"❌ 请求过于频繁 ({provider}): 已达到速率限制"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)
            
        except BadRequestError as e:
            error_msg = f"❌ 请求参数错误: {str(e)}"
            logger.error(f"{error_msg}")
            raise ValueError(error_msg)
            
        except ServiceUnavailableError as e:
            error_msg = f"❌ 服务不可用 ({provider}): {str(e)}"
            logger.error(f"{error_msg}")
            raise ValueError(error_msg)
            
        except Timeout as e:
            error_msg = f"❌ 请求超时 ({provider}): 服务响应时间过长"
            logger.error(f"{error_msg}: {e}")
            raise ValueError(error_msg)
            
        except Exception as e:
            error_msg = f"❌ 补全请求失败: {str(e)}"
            logger.error(f"{error_msg}", exc_info=True)
            raise ValueError(error_msg)
    
    async def get_completion_stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        """获取 AI 补全（流式）"""
        provider = "unknown"
        try:
            # 处理默认模型
            if not request.model or request.model == "default":
                request.model = await self._get_default_model()
                logger.info(f"使用默认模型: {request.model}")

            # 解析模型名称
            provider, model_name = self.parse_model_name(request.model)
            # 规范化请求中的模型，避免重复前缀
            request.model = f"{provider}:{model_name}"
            litellm_model = self.build_litellm_model(provider, model_name)
            
            logger.info(f"请求流式补全: {request.model} -> {litellm_model}")
            
            local_format = None
            if provider == "local":
                local_format = self._detect_local_model_format(model_name)
                if local_format == "gguf" or local_format is None:
                    if not await self._ensure_local_model_ready(model_name):
                        yield f"\n\n[错误] 本地模型 {model_name} 加载失败"
                        return
                elif local_format == "mlx":
                    pass
            
            # 获取厂商配置（OpenAI 兼容厂商需要动态传递配置）
            provider_config = await self.get_provider_config_for_call(provider)
            
            messages = [self._message_to_dict(msg) for msg in request.messages]
            
            mlx_target = None
            if provider == "local" and local_format == "mlx":
                mlx_target = await self._mlx_provider.resolve_target(model_name)
                if mlx_target.mode == "inprocess":
                    mlx_local_provider_cls = _get_mlx_local_provider_cls()
                    if mlx_local_provider_cls is None:
                        yield "\n\n[错误] 未安装 MLX 运行时，无法使用本地 MLX 模型"
                        return
                    mlx = mlx_local_provider_cls()
                    filter_stream = _ThinkStreamFilter()
                    async for piece in mlx.generate_stream(request=request):
                        cleaned = filter_stream.feed(piece)
                        if cleaned:
                            yield cleaned
                    tail = filter_stream.flush()
                    if tail:
                        yield tail
                    return

            params: Dict[str, Any] = {
                "model": litellm_model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "stream": True,
            }
            if request.tools:
                params["tools"] = request.tools
            if request.tool_choice is not None:
                params["tool_choice"] = request.tool_choice
            if request.top_p is not None:
                params["top_p"] = request.top_p
            if request.presence_penalty is not None:
                params["presence_penalty"] = request.presence_penalty
            if request.frequency_penalty is not None:
                params["frequency_penalty"] = request.frequency_penalty
            if request.stop is not None:
                params["stop"] = request.stop
            if request.top_k is not None:
                params["top_k"] = request.top_k
            if provider == "local":
                if mlx_target and mlx_target.mode == "http":
                    params["model"] = mlx_target.litellm_model or params["model"]
                    params["api_base"] = mlx_target.api_base
                    params["api_key"] = "not-needed"
                else:
                    params["api_base"] = self.local_base
                    params["api_key"] = "not-needed"
            elif provider_config:
                params["api_key"] = provider_config["api_key"]
                if "api_base" in provider_config:
                    params["api_base"] = provider_config["api_base"]

            response = await cast(Any, acompletion)(**params)
            stream = cast(Any, response)
            filter_stream = _ThinkStreamFilter()
            async for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                piece = getattr(delta, "content", None) or ""
                cleaned = filter_stream.feed(piece)
                if cleaned:
                    yield cleaned
            tail = filter_stream.flush()
            if tail:
                yield tail
                    
        except AuthenticationError as e:
            error_msg = f"❌ 认证失败 ({provider}): API Key 无效或未配置"
            logger.error(f"{error_msg}: {e}")
            yield f"\n\n[错误] {error_msg}"
            
        except RateLimitError as e:
            error_msg = f"❌ 请求过于频繁 ({provider}): 已达到速率限制"
            logger.error(f"{error_msg}: {e}")
            yield f"\n\n[错误] {error_msg}"
            
        except BadRequestError as e:
            error_msg = f"❌ 请求参数错误: {str(e)}"
            logger.error(f"{error_msg}")
            yield f"\n\n[错误] {error_msg}"
            
        except ServiceUnavailableError as e:
            error_msg = f"❌ 服务不可用 ({provider}): {str(e)}"
            logger.error(f"{error_msg}")
            yield f"\n\n[错误] {error_msg}"
            
        except Timeout as e:
            error_msg = f"❌ 请求超时 ({provider}): 服务响应时间过长"
            logger.error(f"{error_msg}: {e}")
            yield f"\n\n[错误] {error_msg}"
            
        except Exception as e:
            error_msg = f"❌ 流式补全失败: {str(e)}"
            logger.error(f"{error_msg}", exc_info=True)
            yield f"\n\n[错误] {error_msg}"
    
