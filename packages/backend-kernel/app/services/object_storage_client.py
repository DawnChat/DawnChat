from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx


class ObjectStorageClient:
    """Upload artifacts through pre-signed URLs without holding long-lived storage secrets."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=120.0, write=120.0, pool=10.0),
            follow_redirects=True,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def upload_file(
        self,
        *,
        file_path: Path,
        upload_url: str,
        headers: dict[str, str] | None = None,
        method: str = "PUT",
    ) -> None:
        payload = await asyncio.to_thread(file_path.read_bytes)
        response = await self._client.request(
            method.upper(),
            upload_url,
            content=payload,
            headers=headers or {},
        )
        response.raise_for_status()

    async def head(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        response = await self._client.head(url, headers=headers or {})
        response.raise_for_status()
        return response

    async def upload_many(
        self,
        uploads: list[dict[str, Any]],
        on_uploaded: Callable[[int, int, dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> None:
        total = len(uploads)
        for index, item in enumerate(uploads, start=1):
            file_path = Path(str(item["file_path"]))
            upload = item["upload"]
            await self.upload_file(
                file_path=file_path,
                upload_url=str(upload["url"]),
                headers={str(k): str(v) for k, v in dict(upload.get("headers") or {}).items()},
                method=str(upload.get("method") or "PUT"),
            )
            if on_uploaded is not None:
                callback_result = on_uploaded(index, total, item)
                if asyncio.iscoroutine(callback_result):
                    await callback_result