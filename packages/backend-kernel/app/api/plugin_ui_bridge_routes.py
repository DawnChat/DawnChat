from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.plugin_ui_bridge import get_plugin_ui_bridge_service
from app.utils.logger import get_logger

logger = get_logger("plugin_ui_bridge_routes")
router = APIRouter(tags=["PluginUIBridge"])


@router.websocket("/ws/plugin-ui-bridge")
async def plugin_ui_bridge(websocket: WebSocket, plugin_id: str = Query(..., min_length=1)):
    service = get_plugin_ui_bridge_service()
    await websocket.accept()
    await service.register(plugin_id, websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            if isinstance(payload, dict):
                await service.handle_client_message(plugin_id, payload)
    except WebSocketDisconnect:
        logger.info("[plugin_ui_bridge] disconnected plugin=%s", plugin_id)
    except Exception as err:
        logger.error("[plugin_ui_bridge] websocket error plugin=%s error=%s", plugin_id, err, exc_info=True)
    finally:
        await service.unregister(plugin_id, websocket)

