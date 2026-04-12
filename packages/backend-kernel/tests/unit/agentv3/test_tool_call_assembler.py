from __future__ import annotations

from app.agentv3.ai.chunk import ModelChunkV1
from app.agentv3.runtime.tool_call_flow import ToolCallAssembler


def _chunk(**kwargs):
    base = {
        "type": "tool_call_delta",
        "call_id": "",
        "call_index": None,
        "tool_name_delta": "",
        "tool_arguments_delta": "",
    }
    base.update(kwargs)
    return ModelChunkV1(**base)  # type: ignore[arg-type]


def test_assembler_single_call_with_call_id():
    asm = ToolCallAssembler()
    asm.push(_chunk(call_id="c1", tool_name_delta="read", tool_arguments_delta='{"path":'))
    asm.push(_chunk(call_id="c1", tool_arguments_delta='"a.txt"}'))
    out = asm.finalize()
    assert len(out) == 1
    assert out[0].call_id == "c1"
    assert out[0].tool_name == "read"
    assert out[0].raw_arguments == '{"path":"a.txt"}'


def test_assembler_multiple_calls_order_preserved():
    asm = ToolCallAssembler()
    asm.push(_chunk(call_id="a", tool_name_delta="foo"))
    asm.push(_chunk(call_id="b", tool_name_delta="bar", tool_arguments_delta="{}"))
    asm.push(_chunk(call_id="a", tool_arguments_delta="1"))
    out = asm.finalize()
    assert [x.tool_name for x in out] == ["foo", "bar"]
    assert out[0].raw_arguments == "1"


def test_assembler_missing_call_id_uses_index_keys():
    asm = ToolCallAssembler()
    asm.push(_chunk(call_id="", call_index=0, tool_name_delta="t0"))
    asm.push(_chunk(call_id="", call_index=1, tool_name_delta="t1"))
    out = asm.finalize()
    assert len(out) == 2
    assert out[0].tool_name == "t0"
    assert out[1].tool_name == "t1"


def test_assembler_skips_empty_tool_name():
    asm = ToolCallAssembler()
    asm.push(_chunk(call_id="x", tool_name_delta="", tool_arguments_delta="{}"))
    assert asm.finalize() == []


def test_assembler_diagnostics_preview():
    asm = ToolCallAssembler()
    asm.push(_chunk(call_id="z", tool_name_delta="grep", tool_arguments_delta="x" * 200))
    rows = asm.diagnostics()
    assert len(rows) == 1
    assert rows[0]["tool_name"] == "grep"
    assert len(rows[0]["arguments_preview"]) <= 180
