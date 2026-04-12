from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.supabase_session_store import get_supabase_session_store

router = APIRouter(prefix="/supabase-session", tags=["supabase-session"])


class SupabaseSessionPayload(BaseModel):
    access_token: str = Field(..., min_length=1)
    refresh_token: str = ""
    expires_at: Optional[float] = None
    supabase_user_id: Optional[str] = None


@router.post("")
async def put_supabase_session(body: SupabaseSessionPayload) -> dict[str, Any]:
    store = get_supabase_session_store()
    await store.save(
        {
            "access_token": body.access_token,
            "refresh_token": body.refresh_token,
            "expires_at": body.expires_at,
            "supabase_user_id": body.supabase_user_id,
        }
    )
    return {"status": "success"}


@router.delete("")
async def delete_supabase_session() -> dict[str, Any]:
    await get_supabase_session_store().clear()
    return {"status": "success"}
