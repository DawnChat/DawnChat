from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.opencode_mcp_common import JsonRpcRequest
from app.mcp.opencode.hub import OpenCodeMcpHub, OpenCodeMcpHubConfig
from app.services.ddgs_search_mcp_service import get_ddgs_search_mcp_service

router = APIRouter(prefix="/opencode/mcp/search", tags=["opencode-mcp"])

_hub = OpenCodeMcpHub(
    OpenCodeMcpHubConfig(
        mcp_name="search",
        server_name="dawnchat-opencode-search-mcp",
    ),
    service_factory=get_ddgs_search_mcp_service,
)


@router.post("")
async def opencode_mcp_search(body: JsonRpcRequest):
    return await _hub.handle(body)


@router.get("")
async def opencode_mcp_search_info():
    raise HTTPException(status_code=405, detail="Use JSON-RPC POST for MCP calls")
