from __future__ import annotations

import json
from typing import Any, Dict, List

from app.ai.base import Message


class RuntimeRetryPolicy:
    def should_retry_stream_error(self, error_message: str) -> bool:
        text = error_message.lower()
        return "missing corresponding tool call" in text or "last_message_with_tool_calls" in text

    def sanitize_messages_for_retry(self, messages: List[Message], id_factory) -> List[Message]:
        sanitized: List[Message] = []
        pending_tool_calls = False
        for msg in messages:
            if msg.role == "assistant":
                tool_calls = self.normalize_tool_calls_for_model(msg.tool_calls or [], id_factory=id_factory)
                sanitized.append(
                    Message(
                        role="assistant",
                        content=msg.content,
                        name=msg.name,
                        tool_calls=tool_calls or None,
                    )
                )
                pending_tool_calls = bool(tool_calls)
                continue
            if msg.role == "tool":
                if not pending_tool_calls or not msg.tool_call_id:
                    continue
                sanitized.append(
                    Message(
                        role="tool",
                        content=msg.content,
                        name=msg.name,
                        tool_call_id=msg.tool_call_id,
                    )
                )
                pending_tool_calls = False
                continue
            sanitized.append(
                Message(
                    role=msg.role,
                    content=msg.content,
                    name=msg.name,
                    tool_call_id=msg.tool_call_id,
                    tool_calls=self.normalize_tool_calls_for_model(msg.tool_calls or [], id_factory=id_factory) or None,
                )
            )
        return sanitized

    def normalize_tool_calls_for_model(self, tool_calls: List[Dict[str, Any]], id_factory) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            fn = call.get("function")
            if not isinstance(fn, dict):
                continue
            arguments = fn.get("arguments")
            if isinstance(arguments, str):
                safe_arguments = arguments
            else:
                try:
                    safe_arguments = json.dumps(arguments or {}, ensure_ascii=False)
                except Exception:
                    safe_arguments = "{}"
            normalized.append(
                {
                    "id": str(call.get("id") or id_factory("call")),
                    "type": "function",
                    "function": {
                        "name": str(fn.get("name") or ""),
                        "arguments": safe_arguments,
                    },
                }
            )
        return normalized

    def build_stream_error_summary(self, error_message: str) -> str:
        text = (error_message or "").lower()
        if "missing corresponding tool call" in text or "last_message_with_tool_calls" in text:
            return "模型工具调用序列不一致，导致本轮中断。请重试，或先发送一条简短文本以重建上下文。"
        if "unable to convert openai tool calls" in text:
            return "模型工具调用参数格式不兼容，导致本轮中断。请重试，若持续失败请切换模型后继续。"
        return "模型流式调用失败，本轮已停止。请稍后重试，或切换模型继续。"
