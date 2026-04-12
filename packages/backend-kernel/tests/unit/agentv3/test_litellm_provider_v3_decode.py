"""
Golden-style tests for LiteLLMProviderV3 chunk decoding (_decode_chunk and helpers).
Uses synthetic chunk shapes (LiteLLM-normalized / OpenAI-compatible); no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agentv3.ai.litellm_provider_v3 import LiteLLMProviderV3


class _BaseStub:
    """Avoid constructing LiteLLMProvider(); decode tests do not use the base."""


def _provider() -> LiteLLMProviderV3:
    return LiteLLMProviderV3(base_provider=_BaseStub())


def _chunk_with_delta(delta: dict, *, finish_reason=None, message=None):
    choice_kw: dict = {"delta": delta, "finish_reason": finish_reason}
    if message is not None:
        choice_kw["message"] = message
    choice = SimpleNamespace(**choice_kw)
    return SimpleNamespace(choices=[choice])


def test_decode_empty_choices():
    p = _provider()
    assert p._decode_chunk(SimpleNamespace(choices=[])) == []


def test_decode_text_delta_string_content():
    p = _provider()
    chunk = _chunk_with_delta({"content": "hello"})
    out = p._decode_chunk(chunk)
    assert len(out) == 1
    assert out[0].type == "text_delta"
    assert out[0].text == "hello"


def test_decode_text_delta_openai_content_blocks():
    p = _provider()
    delta = {
        "content": [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert [x.type for x in out] == ["text_delta"]
    assert out[0].text == "ab"


def test_decode_reasoning_delta_top_level_field():
    p = _provider()
    out = p._decode_chunk(_chunk_with_delta({"reasoning_content": "step1"}))
    assert len(out) == 1
    assert out[0].type == "reasoning_delta"
    assert out[0].text == "step1"


def test_decode_reasoning_delta_content_blocks():
    p = _provider()
    delta = {
        "content": [
            {"type": "reasoning", "text": "r1"},
            {"type": "thinking", "text": "r2"},
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert [x.type for x in out] == ["reasoning_delta"]
    assert out[0].text == "r1r2"


def test_decode_tool_calls_openai_style():
    p = _provider()
    delta = {
        "tool_calls": [
            {
                "id": "call_abc",
                "index": 0,
                "function": {"name": "read_file", "arguments": '{"path":'},
            }
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert len(out) == 1
    assert out[0].type == "tool_call_delta"
    assert out[0].call_id == "call_abc"
    assert out[0].call_index == 0
    assert out[0].tool_name_delta == "read_file"
    assert out[0].tool_arguments_delta == '{"path":'


def test_decode_tool_calls_arguments_object_json():
    p = _provider()
    delta = {
        "tool_calls": [
            {
                "id": "c1",
                "index": 0,
                "function": {"name": "grep", "arguments": {"pattern": "foo"}},
            }
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert out[0].tool_arguments_delta == '{"pattern": "foo"}'


def test_decode_tool_call_from_content_tool_use_block():
    p = _provider()
    delta = {
        "content": [
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "bash",
                "input": {"cmd": "ls"},
            }
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert len(out) == 1
    assert out[0].type == "tool_call_delta"
    assert out[0].call_id == "tu_1"
    assert out[0].tool_name_delta == "bash"
    assert '"cmd"' in out[0].tool_arguments_delta


def test_decode_fallback_choice_message_with_tool_calls():
    p = _provider()
    delta = {}
    message = {
        "content": "",
        "tool_calls": [
            {"id": "m1", "index": 0, "function": {"name": "final_tool", "arguments": "{}"}},
        ],
    }
    chunk = _chunk_with_delta(delta, message=message)
    out = p._decode_chunk(chunk)
    assert any(x.type == "tool_call_delta" and x.tool_name_delta == "final_tool" for x in out)


def test_decode_provider_specific_fields_nested_text():
    p = _provider()
    delta = {
        "provider_specific_fields": {
            "nested": {
                "content": "from_gemini",
            }
        }
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert any(x.type == "text_delta" and x.text == "from_gemini" for x in out)


def test_decode_provider_specific_fields_thought_placeholder():
    p = _provider()
    delta = {
        "provider_specific_fields": {
            "thought_signatures": ["sig-123"],
            "content": "",
        }
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    reasoning = [x for x in out if x.type == "reasoning_delta"]
    assert reasoning
    assert any(x.text == "思考中..." for x in reasoning)
    assert any(x.metadata.get("placeholder_signature") == "sig-123" for x in reasoning)


@pytest.mark.parametrize(
    "tool_type",
    ["tool_call", "function_call", "tool_use"],
)
def test_decode_content_block_tool_types_accepted(tool_type: str):
    p = _provider()
    delta = {
        "content": [
            {
                "type": tool_type,
                "id": "x",
                "name": "n",
                "arguments": "{}",
            }
        ]
    }
    out = p._decode_chunk(_chunk_with_delta(delta))
    assert len(out) == 1
    assert out[0].type == "tool_call_delta"
    assert out[0].tool_name_delta == "n"


def test_normalize_messages_for_litellm_tool_calls_arguments_object():
    p = _provider()
    messages = [
        {
            "role": "assistant",
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "f", "arguments": {"a": 1}},
                }
            ],
        }
    ]
    norm = p._normalize_messages_for_litellm(messages)
    args = norm[0]["tool_calls"][0]["function"]["arguments"]
    assert isinstance(args, str)
    assert '"a"' in args
