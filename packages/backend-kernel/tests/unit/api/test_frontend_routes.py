import pytest

from app.api import routes


@pytest.mark.asyncio
async def test_frontend_health_returns_ok() -> None:
    response = await routes.frontend_health()
    assert response == {"status": "ok", "name": "DawnChat"}
