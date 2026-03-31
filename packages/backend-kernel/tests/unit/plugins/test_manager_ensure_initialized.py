import pytest

from app.plugins.manager import PluginManager


class _EnsureInitializedDouble:
    def __init__(self, *, initialized: bool, initialize_result: bool) -> None:
        self._initialized = initialized
        self._initialize_result = initialize_result
        self.initialize_calls = 0

    async def initialize(self) -> bool:
        self.initialize_calls += 1
        if self._initialize_result:
            self._initialized = True
        return self._initialize_result


@pytest.mark.asyncio
async def test_ensure_initialized_short_circuits_when_already_initialized() -> None:
    manager = _EnsureInitializedDouble(initialized=True, initialize_result=False)

    result = await PluginManager.ensure_initialized(manager)  # type: ignore[arg-type]

    assert result is True
    assert manager.initialize_calls == 0


@pytest.mark.asyncio
async def test_ensure_initialized_calls_initialize_when_not_initialized() -> None:
    manager = _EnsureInitializedDouble(initialized=False, initialize_result=True)

    result = await PluginManager.ensure_initialized(manager)  # type: ignore[arg-type]

    assert result is True
    assert manager.initialize_calls == 1
    assert manager._initialized is True


@pytest.mark.asyncio
async def test_ensure_initialized_keeps_uninitialized_state_on_failure() -> None:
    manager = _EnsureInitializedDouble(initialized=False, initialize_result=False)

    result = await PluginManager.ensure_initialized(manager)  # type: ignore[arg-type]

    assert result is False
    assert manager.initialize_calls == 1
    assert manager._initialized is False
