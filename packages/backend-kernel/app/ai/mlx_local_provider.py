from abc import ABC, abstractmethod
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

from app.services.model_manager import get_model_manager
from app.utils.json_utils import parse_llm_json
from app.utils.logger import get_logger

from .base import CompletionRequest, _strip_think_blocks, _strip_tool_calls_block, _ThinkStreamFilter
from .mlx_provider import is_mlx_vision_config

_cache: Dict[str, Tuple[Any, Any]] = {}
_locks: Dict[str, asyncio.Lock] = {}
_vlm_cache: Dict[str, Tuple[Any, Any, Any]] = {}
_vlm_locks: Dict[str, asyncio.Lock] = {}
_infer_locks: Dict[str, asyncio.Lock] = {}
logger = get_logger("mlx_local_provider")

def _get_text_from_messages(messages: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    system_parts: List[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        name = m.get("name")
        tool_call_id = m.get("tool_call_id")
        tool_calls = m.get("tool_calls")
        meta_parts: List[str] = []
        if name:
            meta_parts.append(f"name={name}")
        if tool_call_id:
            meta_parts.append(f"tool_call_id={tool_call_id}")
        if tool_calls:
            try:
                import json
                meta_parts.append(json.dumps({"tool_calls": tool_calls}, ensure_ascii=False))
            except Exception:
                pass
        if meta_parts:
            meta_text = "[" + " ".join(meta_parts) + "]"
            if content:
                content = f"{meta_text}\n{content}"
            else:
                content = meta_text
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    txt = item.get("text") or ""
                    if role == "system":
                        system_parts.append(str(txt))
                    else:
                        parts.append(str(txt))
        else:
            txt = content or ""
            if role == "system":
                system_parts.append(str(txt))
            else:
                parts.append(str(txt))
    sys_block = "\n".join(system_parts).strip()
    user_block = "\n".join(parts).strip()
    if sys_block and user_block:
        return sys_block + "\n\n" + user_block
    return sys_block or user_block


class _MLXProviderBase(ABC):
    def __init__(self, model_id: str, load_path: Any):
        self.model_id = model_id
        self.load_path = load_path

    def _coerce_generated_text(self, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (bytes, bytearray)):
            return value.decode("utf-8", errors="replace")
        if isinstance(value, dict):
            try:
                import json
                return json.dumps(value, ensure_ascii=False)
            except Exception:
                return str(value)
        if isinstance(value, str):
            return value
        text = getattr(value, "text", None)
        if text is None:
            text = getattr(value, "generated_text", None)
        if text is None:
            text = getattr(value, "output_text", None)
        if text is None:
            text = getattr(value, "completion", None)
        if text is None and isinstance(value, dict):
            for key in ("text", "generated_text", "output", "completion"):
                if key in value:
                    text = value.get(key)
                    break
        if text is not None:
            if isinstance(text, (bytes, bytearray)):
                return text.decode("utf-8", errors="replace")
            return str(text)
        return str(value)

    def _build_tools_prompt(self, tools: Optional[List[Dict[str, Any]]], tool_choice: Optional[Any]) -> str:
        if not tools:
            return ""
        lines: List[str] = []
        lines.append("工具列表：")
        for t in tools:
            fn = (t.get("function") or {})
            name = str(fn.get("name") or "")
            params = fn.get("parameters")
            lines.append(f"- {name}")
            if isinstance(params, dict):
                try:
                    import json
                    lines.append(json.dumps({"schema": params}, ensure_ascii=False))
                except Exception:
                    pass
        if isinstance(tool_choice, dict):
            fn = tool_choice.get("function") or {}
            tool_name = fn.get("name") or ""
            if tool_name:
                lines.append(f"必须调用工具: {tool_name}")
        elif tool_choice == "none":
            lines.append("禁止调用工具。")
        elif tool_choice in ("auto", "required", None):
            lines.append("当需要工具时，请按以下格式输出：")
            lines.append('{"tool_calls":[{"type":"function","function":{"name":"TOOL_NAME","arguments":{...}}}]}')
        return "\n".join(lines).strip()

    def _coerce_tool_calls(self, obj: Any) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(obj, dict):
            return None
        calls = obj.get("tool_calls") or obj.get("tool_call")
        if isinstance(calls, dict):
            calls = [calls]
        if not isinstance(calls, list):
            return None
        result: List[Dict[str, Any]] = []
        for c in calls:
            if not isinstance(c, dict):
                continue
            f = c.get("function") or {}
            name = f.get("name")
            args = f.get("arguments") or {}
            if isinstance(args, str):
                try:
                    import json
                    args = json.loads(args)
                except Exception:
                    pass
            if not name:
                continue
            result.append({
                "id": c.get("id"),
                "type": c.get("type") or "function",
                "function": {
                    "name": name,
                    "arguments": args
                }
            })
        return result or None

    def _extract_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        obj = parse_llm_json(text)
        return self._coerce_tool_calls(obj)

    def _extract_tool_calls_with_span(self, text: str) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Tuple[int, int]]]:
        import re
        obj = parse_llm_json(text)
        calls = self._coerce_tool_calls(obj)
        if not calls:
            return None, None
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return calls, m.span()
        start = text.find("{")
        if start >= 0:
            return calls, (start, len(text))
        return calls, None

    def _coerce_text_content(self, content: Any) -> str:
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    txt = item.get("text") or ""
                    if txt:
                        parts.append(str(txt))
            return "\n".join(parts)
        if content is None:
            return ""
        return str(content)

    def _normalize_messages(self, messages: List[Dict[str, Any]], tools_prompt: str) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if tools_prompt:
            normalized.append({"role": "system", "content": tools_prompt})
        for m in messages:
            data: Dict[str, Any] = {"role": m.get("role"), "content": self._coerce_text_content(m.get("content"))}
            name = m.get("name")
            tool_call_id = m.get("tool_call_id")
            tool_calls = m.get("tool_calls")
            if name:
                data["name"] = name
            if tool_call_id:
                data["tool_call_id"] = tool_call_id
            if tool_calls:
                data["tool_calls"] = tool_calls
            normalized.append(data)
        return normalized

    def _filter_generate_kwargs(self, generate_fn: Any, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import inspect
            sig = inspect.signature(generate_fn)
            if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
                return {k: v for k, v in kwargs.items() if v is not None}
            allowed = set(sig.parameters.keys())
            return {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        except Exception:
            return {k: v for k, v in kwargs.items() if v is not None}

    def _get_infer_lock(self) -> asyncio.Lock:
        key = str(self.load_path)
        lock = _infer_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _infer_locks[key] = lock
        return lock

    @abstractmethod
    async def _completion_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> str:
        pass

    @abstractmethod
    def _stream_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> AsyncIterator[str]:
        pass

    async def generate_completion(
        self,
        request: CompletionRequest,
        messages: List[Dict[str, Any]]
    ) -> Tuple[str, str, Dict[str, int], Optional[List[Dict[str, Any]]]]:
        tools_prompt = self._build_tools_prompt(request.tools, request.tool_choice)
        text = await self._completion_impl(request, messages, tools_prompt)
        text = self._coerce_generated_text(text)
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        tool_calls, span = self._extract_tool_calls_with_span(text or "")
        if span:
            text = (text[:span[0]] + text[span[1]:]).strip()
        text = _strip_think_blocks(text or "")
        if tool_calls:
            text = _strip_tool_calls_block(text)
        return text or "", "stop", usage, tool_calls

    async def generate_stream(
        self,
        request: CompletionRequest,
        messages: List[Dict[str, Any]]
    ) -> AsyncIterator[str]:
        tools_prompt = self._build_tools_prompt(request.tools, request.tool_choice)
        filter_stream = _ThinkStreamFilter()
        async for piece in self._stream_impl(request, messages, tools_prompt):
            cleaned = filter_stream.feed(piece)
            if cleaned:
                yield cleaned
        tail = filter_stream.flush()
        if tail:
            yield tail


class _MLXTextProvider(_MLXProviderBase):
    async def _ensure_loaded(self) -> Tuple[Any, Any]:
        logger.info("准备加载 MLX 模型: %s", self.model_id)
        try:
            import importlib.util
            if importlib.util.find_spec("mlx_lm") is None:
                raise ValueError("未安装 mlx-lm，无法加载 MLX 模型")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"MLX 运行时初始化失败: {e}") from e
        key = str(self.load_path)
        if key in _cache:
            logger.debug("模型已缓存: %s", key)
            return _cache[key]
        lock = _locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _locks[key] = lock
        async with lock:
            if key in _cache:
                logger.debug("模型在加锁后已缓存: %s", key)
                return _cache[key]
            def _load():
                from mlx_lm import load
                logger.info("开始加载 MLX 模型目录: %s", str(self.load_path))
                return load(str(self.load_path))
            load_result = await asyncio.to_thread(_load)
            if not isinstance(load_result, tuple) or len(load_result) < 2:
                raise ValueError("MLX 模型加载返回值格式不正确")
            model = load_result[0]
            tokenizer = load_result[1]
            _cache[key] = (model, tokenizer)
            logger.info("MLX 模型加载完成: %s", key)
            return model, tokenizer

    def _build_prompt(self, tokenizer: Any, messages: List[Dict[str, Any]], tools_prompt: str) -> str:
        normalized = self._normalize_messages(messages, tools_prompt)
        try:
            apply_fn = getattr(tokenizer, "apply_chat_template", None)
            if apply_fn:
                import inspect
                kwargs: Dict[str, Any] = {"add_generation_prompt": True}
                sig = inspect.signature(apply_fn)
                if "tokenize" in sig.parameters:
                    kwargs["tokenize"] = False
                logger.debug("使用 tokenizer.apply_chat_template 生成提示")
                return apply_fn(normalized, **kwargs)
        except Exception:
            pass
        logger.debug("回退到纯文本提示拼接")
        return _get_text_from_messages(normalized)

    def _build_sampler(self, temperature: Optional[float], top_p: Optional[float], top_k: Optional[int]) -> Any:
        try:
            from mlx_lm import sample_utils
            make_sampler = getattr(sample_utils, "make_sampler", None)
            if not make_sampler:
                return None
            import inspect
            sig = inspect.signature(make_sampler)
            params = sig.parameters
            kwargs: Dict[str, Any] = {}
            if temperature is not None:
                if "temp" in params:
                    kwargs["temp"] = temperature
                elif "temperature" in params:
                    kwargs["temperature"] = temperature
            if top_p is not None and "top_p" in params:
                kwargs["top_p"] = top_p
            if top_k is not None and "top_k" in params:
                kwargs["top_k"] = top_k
            if not kwargs:
                return None
            return make_sampler(**kwargs)
        except Exception:
            return None

    def _truncate_prompt(self, tokenizer: Any, prompt: str, max_tokens: int, context_length: Optional[int]) -> str:
        try:
            tokens = tokenizer.encode(prompt)
            max_ctx = context_length or 65535
            if len(tokens) + max_tokens <= max_ctx:
                return prompt
            keep = max_ctx - max_tokens
            if keep <= 0:
                return ""
            kept_tokens = tokens[-keep:]
            return tokenizer.decode(kept_tokens)
        except Exception:
            return prompt

    async def _completion_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> str:
        model, tokenizer = await self._ensure_loaded()
        prompt = self._build_prompt(tokenizer, messages, tools_prompt)
        prompt = self._truncate_prompt(tokenizer, prompt, request.max_tokens, request.context_length)
        logger.debug("提示长度: %d, max_tokens=%s", len(prompt or ""), str(request.max_tokens))
        def _run():
            from mlx_lm import generate
            sampler = self._build_sampler(request.temperature, request.top_p, request.top_k)
            kwargs = self._filter_generate_kwargs(generate, {
                "max_tokens": request.max_tokens,
                "stop": request.stop,
                "sampler": sampler,
            })
            if sampler is None:
                kwargs = self._filter_generate_kwargs(generate, {
                    **kwargs,
                    "temp": request.temperature,
                    "top_p": request.top_p,
                    "top_k": request.top_k,
                })
            logger.debug("生成参数: %s", str(kwargs))
            return generate(model, tokenizer, prompt, **kwargs)
        logger.info("提交生成任务到线程池")
        async with self._get_infer_lock():
            return await asyncio.to_thread(_run)

    async def _stream_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> AsyncIterator[str]:
        model, tokenizer = await self._ensure_loaded()
        prompt = self._build_prompt(tokenizer, messages, tools_prompt)
        prompt = self._truncate_prompt(tokenizer, prompt, request.max_tokens, request.context_length)
        logger.debug("提示长度: %d, max_tokens=%s", len(prompt or ""), str(request.max_tokens))
        queue: asyncio.Queue[str] = asyncio.Queue()
        done = asyncio.Event()
        loop = asyncio.get_running_loop()
        def _runner():
            try:
                from mlx_lm import stream_generate
                sampler = self._build_sampler(request.temperature, request.top_p, request.top_k)
                kwargs = self._filter_generate_kwargs(stream_generate, {
                    "max_tokens": request.max_tokens,
                    "stop": request.stop,
                    "sampler": sampler,
                })
                if sampler is None:
                    kwargs = self._filter_generate_kwargs(stream_generate, {
                        **kwargs,
                        "temp": request.temperature,
                        "top_p": request.top_p,
                        "top_k": request.top_k,
                    })
                logger.debug("流式生成参数: %s", str(kwargs))
                for resp in stream_generate(model, tokenizer, prompt, **kwargs):
                    piece = getattr(resp, "text", None)
                    if piece:
                        loop.call_soon_threadsafe(queue.put_nowait, piece)
            finally:
                loop.call_soon_threadsafe(done.set)
        async with self._get_infer_lock():
            task = asyncio.create_task(asyncio.to_thread(_runner))
            try:
                while not done.is_set():
                    try:
                        piece = await asyncio.wait_for(queue.get(), timeout=0.2)
                        logger.debug("流式片段长度: %d", len(piece or ""))
                        yield piece
                    except asyncio.TimeoutError:
                        pass
            finally:
                try:
                    await task
                except Exception:
                    pass


class _MLXVLMProvider(_MLXProviderBase):
    def __init__(self, model_id: str, load_path: Any, config: Any):
        super().__init__(model_id, load_path)
        self.config = config

    async def _ensure_loaded(self) -> Tuple[Any, Any, Any]:
        logger.info("准备加载 MLX 视觉模型: %s", self.model_id)
        try:
            import importlib.util
            if importlib.util.find_spec("mlx_vlm") is None:
                raise ValueError("未安装 mlx-vlm，无法加载 MLX 视觉模型")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"MLX VLM 运行时初始化失败: {e}") from e
        key = str(self.load_path)
        if key in _vlm_cache:
            logger.debug("视觉模型已缓存: %s", key)
            return _vlm_cache[key]
        lock = _vlm_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _vlm_locks[key] = lock
        async with lock:
            if key in _vlm_cache:
                logger.debug("视觉模型在加锁后已缓存: %s", key)
                return _vlm_cache[key]
            def _load():
                from mlx_vlm import load
                logger.info("开始加载 MLX 视觉模型目录: %s", str(self.load_path))
                return load(str(self.load_path))
            load_result = await asyncio.to_thread(_load)
            if not isinstance(load_result, tuple) or len(load_result) < 2:
                raise ValueError("MLX 视觉模型加载返回值格式不正确")
            model = load_result[0]
            processor = load_result[1]
            config = load_result[2] if len(load_result) > 2 else getattr(model, "config", None)
            if config is None:
                config = self.config
            _vlm_cache[key] = (model, processor, config)
            logger.info("MLX 视觉模型加载完成: %s", key)
            return model, processor, config

    def _build_prompt(self, processor: Any, config: Any, messages: List[Dict[str, Any]], tools_prompt: str, num_images: int) -> str:
        normalized = self._normalize_messages(messages, tools_prompt)
        prompt = _get_text_from_messages(normalized)
        try:
            from mlx_vlm.prompt_utils import apply_chat_template
            if config is None:
                return prompt
            rendered = apply_chat_template(processor, config, prompt, num_images=num_images)
            if isinstance(rendered, str):
                return rendered
            return str(rendered)
        except Exception:
            return prompt

    def _extract_images(self, messages: List[Dict[str, Any]]) -> List[Any]:
        images: List[Any] = []
        for m in messages:
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") not in ("image_url", "input_image"):
                    continue
                image_url = item.get("image_url")
                if isinstance(image_url, dict):
                    url = image_url.get("url")
                else:
                    url = image_url or item.get("url")
                img = self._load_image(url)
                if img is not None:
                    images.append(img)
        return images

    def _load_image(self, url: Optional[str]) -> Optional[Any]:
        if not url:
            return None
        try:
            import base64
            from io import BytesIO
            from pathlib import Path

            from PIL import Image
            if url.startswith("data:"):
                _, b64 = url.split(",", 1)
                raw = base64.b64decode(b64)
                return Image.open(BytesIO(raw)).convert("RGB")
            if url.startswith("file://"):
                path = Path(url[7:])
                if not path.exists():
                    return None
                return Image.open(path).convert("RGB")
            if url.startswith("http://") or url.startswith("https://"):
                import importlib
                requests = importlib.import_module("requests")
                resp = requests.get(url, timeout=20)
                resp.raise_for_status()
                return Image.open(BytesIO(resp.content)).convert("RGB")
            path = Path(url)
            if path.exists():
                return Image.open(path).convert("RGB")
        except Exception:
            return None
        return None

    def _prepare_vlm_generate(self, generate_fn: Any, images: List[Any], request: CompletionRequest) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
        }
        return self._filter_generate_kwargs(generate_fn, kwargs)

    def _run_vlm_generate(self, generate_fn: Any, model: Any, processor: Any, prompt: str, images: List[Any], request: CompletionRequest) -> str:
        kwargs = self._prepare_vlm_generate(generate_fn, images, request)
        attempts = []
        if images:
            attempts.append({"image": images})
            if len(images) == 1:
                attempts.append({"image": images[0]})
            attempts.append({"images": images})
        attempts.append({})
        last_error = None
        for extra in attempts:
            try:
                return generate_fn(model, processor, prompt, **{**kwargs, **extra})
            except TypeError as e:
                last_error = e
                continue
        if last_error:
            raise last_error
        return ""

    def _run_vlm_stream(
        self,
        stream_fn: Any,
        generate_fn: Any,
        model: Any,
        processor: Any,
        prompt: str,
        images: List[Any],
        request: CompletionRequest,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue
    ) -> None:
        stream_kwargs = self._filter_generate_kwargs(stream_fn, {
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "top_k": request.top_k,
        })
        attempts = []
        if images:
            attempts.append({"image": images})
            if len(images) == 1:
                attempts.append({"image": images[0]})
            attempts.append({"images": images})
        attempts.append({})
        for extra in attempts:
            try:
                for resp in stream_fn(model, processor, prompt, **{**stream_kwargs, **extra}):
                    piece = getattr(resp, "text", None)
                    if piece:
                        loop.call_soon_threadsafe(queue.put_nowait, piece)
                return
            except TypeError:
                continue
            except Exception:
                break
        try:
            text = self._coerce_generated_text(
                self._run_vlm_generate(generate_fn, model, processor, prompt, images, request)
            )
            if text:
                loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception:
            pass

    async def _completion_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> str:
        model, processor, config = await self._ensure_loaded()
        images = self._extract_images(messages)
        prompt = self._build_prompt(processor, config, messages, tools_prompt, num_images=len(images))
        logger.debug("提示长度: %d, max_tokens=%s", len(prompt or ""), str(request.max_tokens))
        def _run():
            from mlx_vlm import generate
            logger.debug("生成参数: %s", str(self._prepare_vlm_generate(generate, images, request)))
            completion = self._run_vlm_generate(generate, model, processor, prompt, images, request)
            logger.debug("VLMCompletion: %s", completion)
            return completion
        logger.info("提交生成任务到线程池")
        async with self._get_infer_lock():
            return await asyncio.to_thread(_run)

    async def _stream_impl(self, request: CompletionRequest, messages: List[Dict[str, Any]], tools_prompt: str) -> AsyncIterator[str]:
        model, processor, config = await self._ensure_loaded()
        images = self._extract_images(messages)
        prompt = self._build_prompt(processor, config, messages, tools_prompt, num_images=len(images))
        queue: asyncio.Queue[str] = asyncio.Queue()
        done = asyncio.Event()
        loop = asyncio.get_running_loop()
        def _runner():
            try:
                import importlib
                module = importlib.import_module("mlx_vlm")
                stream_fn = getattr(module, "stream_generate", None)
                generate_fn = getattr(module, "generate", None)
                if stream_fn and generate_fn:
                    self._run_vlm_stream(stream_fn, generate_fn, model, processor, prompt, images, request, loop, queue)
                elif generate_fn:
                    text = self._run_vlm_generate(generate_fn, model, processor, prompt, images, request)
                    if text:
                        loop.call_soon_threadsafe(queue.put_nowait, text)
            finally:
                loop.call_soon_threadsafe(done.set)
        async with self._get_infer_lock():
            task = asyncio.create_task(asyncio.to_thread(_runner))
            try:
                while not done.is_set():
                    try:
                        piece = await asyncio.wait_for(queue.get(), timeout=0.2)
                        logger.debug("流式片段长度: %d", len(piece or ""))
                        yield piece
                    except asyncio.TimeoutError:
                        pass
            finally:
                try:
                    await task
                except Exception:
                    pass


class MLXLocalProvider:
    def _resolve_load_path(self, model_id: str) -> Any:
        manager = get_model_manager()
        path = manager.get_model_path(model_id)
        if not path:
            raise ValueError(f"模型文件不存在: {model_id}")
        load_path = path
        if path.is_file():
            parent = path.parent
            if (
                (parent / "tokenizer.json").exists()
                or (parent / "tokenizer.model").exists()
                or (parent / "config.json").exists()
            ):
                load_path = parent
        return load_path

    def _read_model_config(self, load_path: Any) -> Dict[str, Any]:
        try:
            import json
            config_path = load_path / "config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f) or {}
        except Exception:
            return {}
        return {}

    def _is_vision_config(self, config: Dict[str, Any]) -> bool:
        return is_mlx_vision_config(config)

    def _create_provider(self, model_id: str) -> _MLXProviderBase:
        load_path = self._resolve_load_path(model_id)
        config = self._read_model_config(load_path)
        if self._is_vision_config(config):
            return _MLXVLMProvider(model_id, load_path, config)
        return _MLXTextProvider(model_id, load_path)

    async def generate_completion(self, request: CompletionRequest) -> Tuple[str, str, Dict[str, int], Optional[List[Dict[str, Any]]]]:
        _, model_id = self._parse_model_key(request.model)
        logger.info("开始非流式生成: model=%s", request.model)
        messages = [self._message_to_dict(m) for m in request.messages]
        provider = self._create_provider(model_id)
        text, finish_reason, usage, tool_calls = await provider.generate_completion(request, messages)
        logger.info("非流式生成完成，输出长度: %d", len(text or ""))
        return text, finish_reason, usage, tool_calls

    async def generate_stream(self, request: CompletionRequest) -> AsyncIterator[str]:
        _, model_id = self._parse_model_key(request.model)
        logger.info("开始流式生成: model=%s", request.model)
        messages = [self._message_to_dict(m) for m in request.messages]
        provider = self._create_provider(model_id)
        async for piece in provider.generate_stream(request, messages):
            yield piece

    def _parse_model_key(self, key: str) -> Tuple[str, str]:
        if ":" in key:
            a, b = key.split(":", 1)
            return a, b
        return "local", key

    def _message_to_dict(self, msg: Any) -> Dict[str, Any]:
        data: Dict[str, Any] = {"role": getattr(msg, "role", None)}
        content = getattr(msg, "content", None)
        if content is None:
            data["content"] = ""
        else:
            data["content"] = content
        name = getattr(msg, "name", None)
        tool_call_id = getattr(msg, "tool_call_id", None)
        tool_calls = getattr(msg, "tool_calls", None)
        if name:
            data["name"] = name
        if tool_call_id:
            data["tool_call_id"] = tool_call_id
        if tool_calls:
            data["tool_calls"] = tool_calls
        return data
