from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

ChunkType = Literal[
    "text_delta",
    "reasoning_delta",
    "tool_call_delta",
    "tool_result_delta",
    "error",
    "end",
]


@dataclass(slots=True)
class ModelChunkV1:
    type: ChunkType
    text: str = ""
    call_id: str = ""
    call_index: Optional[int] = None
    tool_name_delta: str = ""
    tool_arguments_delta: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# Backward compatible alias while v3 runtime migrates to ModelChunkV1 naming.
ModelChunk = ModelChunkV1
