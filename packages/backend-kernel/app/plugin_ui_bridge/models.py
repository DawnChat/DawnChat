from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Dict, Final, Literal, TypedDict

BRIDGE_VERSION: Final[str] = "1"

BridgeOp = Literal[
    "describe",
    "query",
    "act",
    "scroll",
    "capabilities_list",
    "capability_invoke",
    "runtime_info",
    "runtime_refresh",
    "runtime_restart",
]


class BridgeMessageType(StrEnum):
    REQUEST = "bridge.request"
    RESULT = "bridge.result"
    EVENT = "bridge.event"


class BridgeEvent(StrEnum):
    CONTEXT_PUSH = "context_push"
    TTS_SPEAK_ACCEPTED = "tts_speak_accepted"
    TTS_STOPPED = "tts_stopped"


class BridgeOperation(StrEnum):
    DESCRIBE = "describe"
    QUERY = "query"
    ACT = "act"
    SCROLL = "scroll"
    CAPABILITIES_LIST = "capabilities_list"
    CAPABILITY_INVOKE = "capability_invoke"
    RUNTIME_INFO = "runtime_info"
    RUNTIME_REFRESH = "runtime_refresh"
    RUNTIME_RESTART = "runtime_restart"


class UiActionType(StrEnum):
    CLICK = "click"
    TYPE = "type"
    CLEAR_TYPE = "clear_type"
    SCROLL = "scroll"
    SET_VALUE = "set_value"
    FOCUS = "focus"
    PRESS_KEY = "press_key"


class BridgeRequestEnvelope(TypedDict):
    type: str
    version: str
    requestId: str
    pluginId: str
    op: str
    payload: Dict[str, Any]


class BridgeEventEnvelope(TypedDict):
    type: str
    version: str
    pluginId: str
    event: str
    payload: Dict[str, Any]


@dataclass(slots=True)
class BridgeRequest:
    request_id: str
    plugin_id: str
    op: BridgeOperation
    payload: Dict[str, Any]


def make_request_envelope(request: BridgeRequest) -> BridgeRequestEnvelope:
    return {
        "type": BridgeMessageType.REQUEST.value,
        "version": BRIDGE_VERSION,
        "requestId": request.request_id,
        "pluginId": request.plugin_id,
        "op": request.op.value,
        "payload": request.payload,
    }


def make_event_envelope(
    plugin_id: str,
    event: BridgeEvent,
    payload: Dict[str, Any],
) -> BridgeEventEnvelope:
    return {
        "type": BridgeMessageType.EVENT.value,
        "version": BRIDGE_VERSION,
        "pluginId": plugin_id,
        "event": event.value,
        "payload": payload,
    }
