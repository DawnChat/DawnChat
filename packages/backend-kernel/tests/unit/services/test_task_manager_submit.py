"""Tests for TaskManager.submit optional caller-provided task_id."""

import asyncio
from collections.abc import Iterator

import pytest

import app.services.task_manager as task_manager_module
from app.services.task_manager import TaskManager


@pytest.fixture
def fresh_task_manager() -> Iterator[TaskManager]:
    """Use a fresh TaskManager for this module; restore module-level singleton after each test."""
    previous_instance = TaskManager._instance
    previous_module_ref = task_manager_module._task_manager
    TaskManager._instance = None
    task_manager_module._task_manager = None
    tm = TaskManager()
    yield tm
    TaskManager._instance = previous_instance
    task_manager_module._task_manager = previous_module_ref


@pytest.mark.asyncio
async def test_submit_uses_explicit_task_id(fresh_task_manager: TaskManager) -> None:
    tm = fresh_task_manager
    done = asyncio.Event()

    async def work() -> int:
        done.set()
        return 7

    tid = "a1b2c3d4"
    out = await tm.submit(
        tool_name="unit noop",
        arguments={},
        plugin_id="host",
        executor_func=lambda: work(),
        task_id=tid,
    )
    assert out == tid
    await asyncio.wait_for(done.wait(), timeout=2.0)
    await asyncio.sleep(0.05)
    info = tm.get_task(tid)
    assert info is not None
    assert info.task_id == tid
    assert info.status.value == "completed"
    assert info.result == 7


@pytest.mark.asyncio
async def test_submit_rejects_duplicate_explicit_task_id(fresh_task_manager: TaskManager) -> None:
    tm = fresh_task_manager
    tid = "feedface"

    async def work() -> None:
        return None

    await tm.submit(
        tool_name="first",
        arguments={},
        plugin_id="host",
        executor_func=lambda: work(),
        task_id=tid,
    )
    await asyncio.sleep(0.05)

    with pytest.raises(ValueError, match="already exists"):
        await tm.submit(
            tool_name="second",
            arguments={},
            plugin_id="host",
            executor_func=lambda: work(),
            task_id=tid,
        )


@pytest.mark.asyncio
async def test_submit_rejects_blank_explicit_task_id(fresh_task_manager: TaskManager) -> None:
    tm = fresh_task_manager

    async def work() -> None:
        return None

    with pytest.raises(ValueError, match="must not be empty"):
        await tm.submit(
            tool_name="t",
            arguments={},
            plugin_id="host",
            executor_func=lambda: work(),
            task_id="   ",
        )
