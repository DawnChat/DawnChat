from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig
from app.services.iwp_mcp_service import get_iwp_mcp_service

router = APIRouter(prefix="/opencode/mcp/iwp", tags=["opencode-mcp"])

_hub = OpenCodeMcpHub(
    OpenCodeMcpHubConfig(
        mcp_name="iwp",
        server_name="dawnchat-opencode-iwp-mcp",
    ),
    service_factory=lambda: get_iwp_mcp_service(),
)


@router.post("")
async def opencode_mcp_iwp(body: JsonRpcRequest):
    return await _hub.handle(body)


@router.get("")
async def opencode_mcp_iwp_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
