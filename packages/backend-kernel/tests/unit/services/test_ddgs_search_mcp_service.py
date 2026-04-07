import pytest

from app.services import ddgs_search_mcp_service as service_module
from app.services.ddgs_search_mcp_service import DdgsSearchMcpService


class _FakeDdgsClient:
    call_count = 0

    def __init__(self, timeout: int = 8):
        self.timeout = timeout

    def text(self, **kwargs):
        _FakeDdgsClient.call_count += 1
        return [{"title": "Hello", "href": "https://example.com", "body": "snippet"}]

    def images(self, **kwargs):
        return [{"title": "Img", "image": "https://img.example.com", "thumbnail": "https://thumb.example.com"}]

    def videos(self, **kwargs):
        return [{"title": "Video", "content": "https://video.example.com", "description": "desc"}]

    def extract(self, url: str, fmt: str = "text_markdown"):
        return {"url": url, "content": f"content:{fmt}"}


class _NoImageResultDdgsClient(_FakeDdgsClient):
    def images(self, **kwargs):
        raise RuntimeError("No results found.")


class _ImageFallbackDdgsClient(_FakeDdgsClient):
    def __init__(self, timeout: int = 8):
        super().__init__(timeout=timeout)
        self._image_call_count = 0

    def images(self, **kwargs):
        self._image_call_count += 1
        if self._image_call_count == 1:
            raise RuntimeError("No results found.")
        return [
            {
                "title": f"fallback-{kwargs.get('region')}",
                "image": "https://img.example.com/fallback",
                "thumbnail": "https://thumb.example.com/fallback",
            }
        ]


@pytest.mark.asyncio
async def test_execute_text_returns_normalized_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "DDGS", _FakeDdgsClient)
    monkeypatch.setattr(service_module.Config, "DDGS_CACHE_ENABLED", False)
    service = DdgsSearchMcpService()
    result = await service.execute("dawnchat.search.text", {"query": "python"})
    assert result["ok"] is True
    assert result["data"]["items"][0]["title"] == "Hello"
    assert result["data"]["cache_hit"] is False


@pytest.mark.asyncio
async def test_execute_extract_rejects_invalid_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "DDGS", _FakeDdgsClient)
    service = DdgsSearchMcpService()
    result = await service.execute("dawnchat.search.extract", {"url": "file:///tmp/demo"})
    assert result["ok"] is False
    assert result["error_code"] == "invalid_arguments"


@pytest.mark.asyncio
async def test_execute_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeDdgsClient.call_count = 0
    monkeypatch.setattr(service_module, "DDGS", _FakeDdgsClient)
    monkeypatch.setattr(service_module.Config, "DDGS_CACHE_ENABLED", True)
    monkeypatch.setattr(service_module.Config, "DDGS_CACHE_MAX_ENTRIES", 10)
    monkeypatch.setattr(service_module.Config, "DDGS_SEARCH_CACHE_TTL_SECONDS", 60)
    service = DdgsSearchMcpService()

    first = await service.execute("dawnchat.search.text", {"query": "cache"})
    second = await service.execute("dawnchat.search.text", {"query": "cache"})

    assert first["ok"] is True
    assert second["ok"] is True
    assert first["data"]["cache_hit"] is False
    assert second["data"]["cache_hit"] is True
    assert _FakeDdgsClient.call_count == 1


@pytest.mark.asyncio
async def test_execute_image_no_results_returns_empty_items(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "DDGS", _NoImageResultDdgsClient)
    monkeypatch.setattr(service_module.Config, "DDGS_CACHE_ENABLED", False)
    service = DdgsSearchMcpService()
    result = await service.execute("dawnchat.search.image", {"query": "cat"})
    assert result["ok"] is True
    assert result["data"]["no_results"] is True
    assert result["data"]["items"] == []


@pytest.mark.asyncio
async def test_execute_image_fallback_retry_can_recover_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service_module, "DDGS", _ImageFallbackDdgsClient)
    monkeypatch.setattr(service_module.Config, "DDGS_CACHE_ENABLED", False)
    monkeypatch.setattr(service_module.Config, "DDGS_IMAGE_FALLBACK_REGION", "wt-wt")
    monkeypatch.setattr(service_module.Config, "DDGS_IMAGE_FALLBACK_SAFESEARCH", "moderate")
    service = DdgsSearchMcpService()
    result = await service.execute(
        "dawnchat.search.image",
        {"query": "cat", "region": "us-en", "safesearch": "off"},
    )
    assert result["ok"] is True
    assert result["data"]["fallback_used"] is True
    assert result["data"]["requested_region"] == "us-en"
    assert result["data"]["region"] == "wt-wt"
    assert len(result["data"]["items"]) == 1
