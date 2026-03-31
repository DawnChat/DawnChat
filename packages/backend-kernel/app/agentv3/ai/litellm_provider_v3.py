from __future__ import annotations

import json
from typing import Any, AsyncIterator, Dict, List, Optional, cast

from app.ai.base import CompletionRequest
from app.utils.logger import get_logger

from .chunk import ModelChunkV1
from .thinking import build_provider_thinking_options

logger = get_logger(__name__)


class LiteLLMProviderV3:
    """
    AgentV3 dedicated structured stream provider.
    """

    def __init__(self, base_provider: Optional[Any] = None):
        if base_provider is not None:
            self._base = base_provider
            return
        from app.ai.litellm_provider import LiteLLMProvider

        self._base = LiteLLMProvider()

    async def stream(self, request: CompletionRequest) -> AsyncIterator[ModelChunkV1]:
        provider = "unknown"
        try:
            from litellm import acompletion
            from litellm.exceptions import (
                AuthenticationError,
                BadRequestError,
                RateLimitError,
                ServiceUnavailableError,
                Timeout,
            )

            if not request.model or request.model == "default":
                request.model = await self._base._get_default_model()

            provider, model_name = self._base.parse_model_name(request.model)
            request.model = f"{provider}:{model_name}"
            litellm_model = self._base.build_litellm_model(provider, model_name)
            litellm_version = self._resolve_litellm_version()
            logger.info(
                "agentv3 stream request model=%s provider=%s litellm=%s tools=%s tool_choice=%s context_length=%s",
                litellm_model,
                provider,
                litellm_version,
                bool(request.tools),
                request.tool_choice,
                request.context_length,
            )

            messages = [self._base._message_to_dict(msg) for msg in request.messages]
            messages = self._normalize_messages_for_litellm(messages)

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
            if request.context_length is not None:
                params["context_length"] = request.context_length
            params = self._apply_provider_options(
                params=params,
                provider=provider,
                model_name=model_name,
                provider_options=request.provider_options or {},
            )

            provider_config = await self._base.get_provider_config_for_call(provider)
            if provider == "local":
                params["api_base"] = self._base.local_base
                params["api_key"] = "not-needed"
            elif provider_config:
                params["api_key"] = provider_config["api_key"]
                if "api_base" in provider_config:
                    params["api_base"] = provider_config["api_base"]

            response = await cast(Any, acompletion)(**params)
            stream = cast(Any, response)
            chunk_index = 0
            async for chunk in stream:
                chunk_index += 1
                logger.debug(
                    "agentv3 raw stream chunk index=%s payload=%s",
                    chunk_index,
                    self._serialize_chunk_for_debug(chunk),
                )
                for out in self._decode_chunk(chunk):
                    yield out
            yield ModelChunkV1(type="end")
        except ImportError as err:
            logger.error("agentv3 stream import error: %s", err)
            yield ModelChunkV1(type="error", error="provider_import_error")
        except AuthenticationError as err:
            logger.error("agentv3 stream auth error: %s", err)
            yield ModelChunkV1(type="error", error="auth_error")
        except RateLimitError as err:
            logger.error("agentv3 stream rate-limit error: %s", err)
            yield ModelChunkV1(type="error", error="rate_limit_error")
        except BadRequestError as err:
            logger.error("agentv3 stream bad-request error: %s", err)
            yield ModelChunkV1(type="error", error=f"bad_request: {err}")
        except ServiceUnavailableError as err:
            logger.error("agentv3 stream service unavailable: %s", err)
            yield ModelChunkV1(type="error", error="service_unavailable")
        except Timeout as err:
            logger.error("agentv3 stream timeout: %s", err)
            yield ModelChunkV1(type="error", error="timeout")
        except Exception as err:
            logger.error("agentv3 stream unknown error: %s", err, exc_info=True)
            yield ModelChunkV1(type="error", error=f"unknown: {err}")

    def _resolve_litellm_version(self) -> str:
        try:
            import litellm

            value = getattr(litellm, "__version__", None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
        try:
            from importlib.metadata import version

            value = version("litellm")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:
            pass
        return "unknown"

    def _decode_chunk(self, chunk: Any) -> list[ModelChunkV1]:
        result: list[ModelChunkV1] = []
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return result

        choice = choices[0]
        delta = getattr(choice, "delta", None) or {}
        metadata: Dict[str, Any] = {}
        if hasattr(choice, "finish_reason") and getattr(choice, "finish_reason") is not None:
            metadata["finish_reason"] = getattr(choice, "finish_reason")

        text_delta = self._extract_text_delta(delta)
        if text_delta:
            result.append(ModelChunkV1(type="text_delta", text=text_delta, metadata=dict(metadata)))

        reasoning_delta = self._extract_reasoning_delta(delta)
        if reasoning_delta:
            result.append(ModelChunkV1(type="reasoning_delta", text=reasoning_delta, metadata=dict(metadata)))

        tool_call_deltas = self._extract_tool_call_deltas(delta)
        if not tool_call_deltas:
            # Some gateways encode tool call blocks inside content instead of delta.tool_calls.
            tool_call_deltas = self._extract_tool_call_from_content(delta)
        result.extend(tool_call_deltas)
        if not result:
            # Gemini/LiteLLM may place stream payload under provider_specific_fields.
            result.extend(self._extract_from_provider_specific_fields(delta, metadata))
        if not result:
            # Some providers attach final assistant payload on choice.message.
            result.extend(self._extract_from_choice_message(choice, metadata))
        if not result:
            try:
                delta_keys = list(delta.keys()) if isinstance(delta, dict) else list(vars(delta).keys())
            except Exception:
                delta_keys = []
            provider_field_keys: list[str] = []
            try:
                provider_fields = (
                    delta.get("provider_specific_fields")
                    if isinstance(delta, dict)
                    else getattr(delta, "provider_specific_fields", None)
                )
                if isinstance(provider_fields, dict):
                    provider_field_keys = list(provider_fields.keys())
            except Exception:
                provider_field_keys = []
            if delta_keys:
                logger.debug(
                    "agentv3 decode chunk produced no delta keys=%s provider_specific_fields_keys=%s",
                    delta_keys,
                    provider_field_keys,
                )
        return result

    def _extract_from_choice_message(self, choice: Any, metadata: Dict[str, Any]) -> list[ModelChunkV1]:
        message = getattr(choice, "message", None)
        if not message:
            return []
        if isinstance(message, dict):
            content = message.get("content")
            tool_calls = message.get("tool_calls")
        else:
            content = getattr(message, "content", None)
            tool_calls = getattr(message, "tool_calls", None)
        synthetic_delta: Dict[str, Any] = {}
        if content is not None:
            synthetic_delta["content"] = content
        if tool_calls is not None:
            synthetic_delta["tool_calls"] = tool_calls
        if not synthetic_delta:
            return []
        outputs: list[ModelChunkV1] = []
        text_delta = self._extract_text_delta(synthetic_delta)
        if text_delta:
            outputs.append(ModelChunkV1(type="text_delta", text=text_delta, metadata=dict(metadata)))
        reasoning_delta = self._extract_reasoning_delta(synthetic_delta)
        if reasoning_delta:
            outputs.append(ModelChunkV1(type="reasoning_delta", text=reasoning_delta, metadata=dict(metadata)))
        tool_call_deltas = self._extract_tool_call_deltas(synthetic_delta)
        if not tool_call_deltas:
            tool_call_deltas = self._extract_tool_call_from_content(synthetic_delta)
        outputs.extend(tool_call_deltas)
        return outputs

    def _extract_from_provider_specific_fields(self, delta: Any, metadata: Dict[str, Any]) -> list[ModelChunkV1]:
        if isinstance(delta, dict):
            provider_fields = delta.get("provider_specific_fields")
        else:
            provider_fields = getattr(delta, "provider_specific_fields", None)
        if not provider_fields:
            return []
        outputs: list[ModelChunkV1] = []
        tool_dedupe: set[tuple[str, Optional[int], str, str]] = set()
        for node in self._iter_candidate_nodes(provider_fields):
            text_delta = self._extract_text_delta(node)
            if text_delta:
                outputs.append(ModelChunkV1(type="text_delta", text=text_delta, metadata=dict(metadata)))
            reasoning_delta = self._extract_reasoning_delta(node)
            if reasoning_delta:
                outputs.append(ModelChunkV1(type="reasoning_delta", text=reasoning_delta, metadata=dict(metadata)))
            tool_call_deltas = self._extract_tool_call_deltas(node)
            if not tool_call_deltas:
                tool_call_deltas = self._extract_tool_call_from_content(node)
            for piece in tool_call_deltas:
                key = (piece.call_id, piece.call_index, piece.tool_name_delta, piece.tool_arguments_delta)
                if key in tool_dedupe:
                    continue
                tool_dedupe.add(key)
                outputs.append(piece)
        placeholder_signature = self._extract_thought_signature(provider_fields)
        if placeholder_signature:
            has_reasoning = any(piece.type == "reasoning_delta" for piece in outputs)
            if not has_reasoning:
                placeholder_metadata = dict(metadata)
                placeholder_metadata["placeholder_signature"] = placeholder_signature
                outputs.append(ModelChunkV1(type="reasoning_delta", text="思考中...", metadata=placeholder_metadata))
        if outputs:
            logger.debug("agentv3 extracted deltas from provider_specific_fields count=%s", len(outputs))
        return outputs

    def _apply_provider_options(
        self,
        *,
        params: Dict[str, Any],
        provider: str,
        model_name: str,
        provider_options: Dict[str, Any],
    ) -> Dict[str, Any]:
        enabled = bool(provider_options.get("thinking_enabled"))
        effort = provider_options.get("thinking_effort")
        budget_tokens = provider_options.get("thinking_budget_tokens")
        thinking_options = build_provider_thinking_options(
            provider=provider,
            model_name=model_name,
            enabled=enabled,
            effort=effort if isinstance(effort, str) else None,
            budget_tokens=budget_tokens if isinstance(budget_tokens, int) else None,
        )
        if not thinking_options.get("enabled"):
            return params
        thinking_payload = thinking_options.get("thinking")
        if isinstance(thinking_payload, dict):
            params["thinking"] = thinking_payload
        reasoning_effort = thinking_options.get("reasoning_effort")
        if isinstance(reasoning_effort, str) and reasoning_effort:
            params["reasoning_effort"] = reasoning_effort
        reasoning_summary = thinking_options.get("reasoning_summary")
        if isinstance(reasoning_summary, str) and reasoning_summary:
            params["reasoning_summary"] = reasoning_summary
        extra_body = dict(params.get("extra_body") or {})
        thinking_config = thinking_options.get("thinking_config")
        if isinstance(thinking_config, dict):
            extra_body["thinkingConfig"] = thinking_config
        if extra_body:
            params["extra_body"] = extra_body
        logger.info(
            "agentv3 thinking options applied provider=%s model=%s enabled=%s effort=%s budget=%s keys=%s",
            provider,
            model_name,
            enabled,
            effort,
            budget_tokens,
            sorted([k for k in ["thinking", "reasoning_effort", "reasoning_summary", "extra_body"] if k in params]),
        )
        return params

    def _extract_thought_signature(self, provider_fields: Any) -> str:
        if isinstance(provider_fields, dict):
            signatures = provider_fields.get("thought_signatures")
            if isinstance(signatures, list):
                for item in signatures:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
        for node in self._iter_candidate_nodes(provider_fields):
            if not isinstance(node, dict):
                continue
            signatures = node.get("thought_signatures")
            if not isinstance(signatures, list):
                continue
            for item in signatures:
                if isinstance(item, str) and item.strip():
                    return item.strip()
        return ""

    def _iter_candidate_nodes(self, root: Any) -> List[Any]:
        queue: List[Any] = [root]
        nodes: List[Any] = []
        visited: set[int] = set()
        while queue and len(nodes) < 64:
            current = queue.pop(0)
            obj_id = id(current)
            if obj_id in visited:
                continue
            visited.add(obj_id)
            nodes.append(current)
            if isinstance(current, dict):
                for value in current.values():
                    if isinstance(value, (dict, list)):
                        queue.append(value)
                continue
            if isinstance(current, list):
                for item in current:
                    if isinstance(item, (dict, list)):
                        queue.append(item)
        return nodes

    def _extract_tool_call_from_content(self, delta: Any) -> list[ModelChunkV1]:
        raw_content = delta.get("content") if isinstance(delta, dict) else getattr(delta, "content", None)
        if not isinstance(raw_content, list):
            return []
        outputs: list[ModelChunkV1] = []
        for idx, item in enumerate(raw_content):
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").lower()
            if item_type not in {"tool_call", "function_call", "tool_use"}:
                continue
            call_id = str(item.get("id") or item.get("call_id") or "")
            name = str(
                item.get("name")
                or item.get("tool_name")
                or ((item.get("function") or {}) if isinstance(item.get("function"), dict) else {}).get("name")
                or ""
            )
            raw_args: Any = (
                item.get("arguments")
                or item.get("args")
                or item.get("input")
                or ((item.get("function") or {}) if isinstance(item.get("function"), dict) else {}).get("arguments")
                or {}
            )
            if isinstance(raw_args, str):
                args_delta = raw_args
            else:
                try:
                    args_delta = json.dumps(raw_args, ensure_ascii=False)
                except Exception:
                    args_delta = "{}"
            if not name and not args_delta:
                continue
            outputs.append(
                ModelChunkV1(
                    type="tool_call_delta",
                    call_id=call_id,
                    call_index=idx,
                    tool_name_delta=name,
                    tool_arguments_delta=args_delta,
                )
            )
        if outputs:
            logger.debug("agentv3 extracted tool_call from content blocks count=%s", len(outputs))
        return outputs

    def _normalize_messages_for_litellm(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for msg in messages:
            cloned: Dict[str, Any] = dict(msg)
            raw_calls = cloned.get("tool_calls")
            if isinstance(raw_calls, list):
                out_calls: List[Dict[str, Any]] = []
                for call in raw_calls:
                    if not isinstance(call, dict):
                        continue
                    call_copy: Dict[str, Any] = dict(call)
                    fn = call_copy.get("function")
                    if isinstance(fn, dict):
                        fn_copy: Dict[str, Any] = dict(fn)
                        args = fn_copy.get("arguments")
                        if isinstance(args, str):
                            fn_copy["arguments"] = args
                        elif args is None:
                            fn_copy["arguments"] = "{}"
                        else:
                            try:
                                fn_copy["arguments"] = json.dumps(args, ensure_ascii=False)
                            except Exception:
                                fn_copy["arguments"] = "{}"
                        call_copy["function"] = fn_copy
                    out_calls.append(call_copy)
                cloned["tool_calls"] = out_calls
            normalized.append(cloned)
        return normalized

    def _extract_text_delta(self, delta: Any) -> str:
        if isinstance(delta, dict):
            content = delta.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    item_type = str(item.get("type") or "").lower()
                    if item_type and item_type not in {"text", "output_text", "input_text"}:
                        continue
                    value = item.get("text")
                    if isinstance(value, str) and value:
                        parts.append(value)
                        continue
                    if isinstance(value, dict):
                        nested = value.get("value")
                        if isinstance(nested, str) and nested:
                            parts.append(nested)
                            continue
                    alt = item.get("content")
                    if isinstance(alt, str) and alt:
                        parts.append(alt)
                if parts:
                    return "".join(parts)
            if isinstance(content, dict):
                value = content.get("text")
                if isinstance(value, str):
                    return value
                if isinstance(value, dict):
                    nested = value.get("value")
                    if isinstance(nested, str):
                        return nested
            return ""
        content = getattr(delta, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            content_parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if item_type and item_type not in {"text", "output_text", "input_text"}:
                    continue
                value = item.get("text")
                if isinstance(value, str) and value:
                    content_parts.append(value)
                    continue
                if isinstance(value, dict):
                    nested = value.get("value")
                    if isinstance(nested, str) and nested:
                        content_parts.append(nested)
                        continue
                alt = item.get("content")
                if isinstance(alt, str) and alt:
                    content_parts.append(alt)
            if content_parts:
                return "".join(content_parts)
        if isinstance(content, dict):
            value = content.get("text")
            if isinstance(value, str):
                return value
            if isinstance(value, dict):
                nested = value.get("value")
                if isinstance(nested, str):
                    return nested
        return ""

    def _extract_reasoning_delta(self, delta: Any) -> str:
        candidates = [
            "reasoning",
            "reasoning_content",
            "reasoningContent",
            "thinking",
            "analysis",
            "thinking_delta",
            "reasoning_delta",
        ]
        for field in candidates:
            if isinstance(delta, dict):
                value = delta.get(field)
            else:
                value = getattr(delta, field, None)
            if isinstance(value, str) and value:
                return value
        # Some providers return reasoning as block arrays.
        raw_content = delta.get("content") if isinstance(delta, dict) else getattr(delta, "content", None)
        if isinstance(raw_content, list):
            parts: list[str] = []
            for item in raw_content:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").lower()
                if item_type in {"reasoning", "thinking", "analysis"}:
                    text = item.get("text")
                    if isinstance(text, str) and text:
                        parts.append(text)
            if parts:
                return "".join(parts)
        return ""

    def _extract_tool_call_deltas(self, delta: Any) -> list[ModelChunkV1]:
        raw_calls = None
        if isinstance(delta, dict):
            raw_calls = delta.get("tool_calls")
        else:
            raw_calls = getattr(delta, "tool_calls", None)
        if not raw_calls:
            return []

        outputs: list[ModelChunkV1] = []
        for raw in raw_calls:
            if isinstance(raw, dict):
                idx = raw.get("index")
                call_id = str(raw.get("id") or "")
                fn = raw.get("function") or {}
                name_delta = ""
                args_delta = ""
                if isinstance(fn, dict):
                    name_val = fn.get("name")
                    args_val = fn.get("arguments")
                    if isinstance(name_val, str):
                        name_delta = name_val
                    if isinstance(args_val, str):
                        args_delta = args_val
                    elif args_val is not None:
                        try:
                            args_delta = json.dumps(args_val, ensure_ascii=False)
                        except Exception:
                            args_delta = "{}"
                if not name_delta and isinstance(raw.get("name"), str):
                    name_delta = str(raw.get("name"))
                if not args_delta and raw.get("arguments") is not None:
                    if isinstance(raw.get("arguments"), str):
                        args_delta = str(raw.get("arguments"))
                    else:
                        try:
                            args_delta = json.dumps(raw.get("arguments"), ensure_ascii=False)
                        except Exception:
                            args_delta = "{}"
            else:
                idx = getattr(raw, "index", None)
                call_id = str(getattr(raw, "id", "") or "")
                fn = getattr(raw, "function", None)
                name_delta = ""
                args_delta = ""
                if fn is not None:
                    name_val = getattr(fn, "name", None)
                    args_val = getattr(fn, "arguments", None)
                    if isinstance(name_val, str):
                        name_delta = name_val
                    if isinstance(args_val, str):
                        args_delta = args_val
                    elif args_val is not None:
                        try:
                            args_delta = json.dumps(args_val, ensure_ascii=False)
                        except Exception:
                            args_delta = "{}"
                if not name_delta:
                    alt_name = getattr(raw, "name", None)
                    if isinstance(alt_name, str):
                        name_delta = alt_name

            outputs.append(
                ModelChunkV1(
                    type="tool_call_delta",
                    call_id=call_id,
                    call_index=int(idx) if isinstance(idx, int) else None,
                    tool_name_delta=name_delta,
                    tool_arguments_delta=args_delta,
                )
            )
        return outputs

    def _serialize_chunk_for_debug(self, chunk: Any) -> str:
        try:
            jsonable = self._to_jsonable(chunk)
            return json.dumps(jsonable, ensure_ascii=False)
        except Exception as err:
            return f"<serialize_failed error={err!r} raw={chunk!r}>"

    def _to_jsonable(self, value: Any, depth: int = 0) -> Any:
        if depth > 10:
            return "<max_depth_reached>"
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            return {str(k): self._to_jsonable(v, depth + 1) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._to_jsonable(item, depth + 1) for item in value]
        if hasattr(value, "model_dump"):
            try:
                dumped = value.model_dump()
                return self._to_jsonable(dumped, depth + 1)
            except Exception:
                pass
        if hasattr(value, "dict"):
            try:
                dumped = value.dict()
                return self._to_jsonable(dumped, depth + 1)
            except Exception:
                pass
        if hasattr(value, "__dict__"):
            try:
                data = vars(value)
                return {str(k): self._to_jsonable(v, depth + 1) for k, v in data.items()}
            except Exception:
                pass
        try:
            return repr(value)
        except Exception:
            return "<unreprable>"
