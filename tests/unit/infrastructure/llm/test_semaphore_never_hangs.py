"""Admission control must never wait forever.

``DynamicLLMSemaphore.acquire`` queues a task it cannot fit and then polls
``while True: await asyncio.sleep(0.1)`` with no timeout and no escape. The
condition it polls is ``used + required <= available``. If ``required`` alone
exceeds total capacity, that is unsatisfiable even with the machine completely
idle -- so the loop spins forever.

This is exactly what happened in CI: three jobs hit the six-hour ceiling and were
killed, with pytest left as an orphan process. On a runner with no GPU and modest
RAM, the estimated footprint of a model exceeded capacity and the first call
never returned.

The defect predates the move to victor's providers -- the old Ollama client used
the same context manager -- but nothing exercised it from a test, so it stayed
invisible until the client had unit coverage.
"""

from __future__ import annotations

import asyncio

import pytest

from investigator.infrastructure.llm.semaphore import DynamicLLMSemaphore


def _semaphore(available_gb: float) -> DynamicLLMSemaphore:
    """A semaphore with a known capacity, bypassing host detection."""
    sem = DynamicLLMSemaphore.__new__(DynamicLLMSemaphore)
    sem.available_vram_gb = available_gb
    sem.total_vram_gb = available_gb
    sem.used_vram_gb = 0.0
    sem.active_tasks = {}
    sem.active_tasks_per_model = {}
    sem.loaded_models = set()
    sem.queue = []
    sem._lock = asyncio.Lock()
    sem._stats = {
        "total_requests": 0,
        "queue_waits": 0,
        "cache_hits": 0,
        "concurrent_peak": 0,
        "vram_peak": 0,
    }
    sem.model_specs = {}
    sem.model_vram_requirements = {"small": 0.5, "enormous-model": 500.0}
    sem.task_complexity = {}
    sem.cache_reduction_factor = 0.6
    sem.reserved_vram_gb = 0.0
    return sem


@pytest.mark.asyncio
async def test_a_task_larger_than_total_capacity_does_not_hang():
    """The unsatisfiable case must resolve, not spin.

    Waiting on ``used + required <= available`` when ``required > available`` is
    a condition no amount of waiting can make true.
    """
    sem = _semaphore(available_gb=1.0)

    # 1GB of capacity, and a task estimated far above it.
    allocation_id = await asyncio.wait_for(
        sem.acquire(model="enormous-model", task_type="synthesis", response_tokens=100_000),
        timeout=10.0,
    )

    assert allocation_id, "acquire returned no allocation"
    sem.release(allocation_id)


@pytest.mark.asyncio
async def test_an_oversized_task_waits_for_the_machine_to_be_idle():
    """It may run, but not alongside something else -- that is the whole point."""
    sem = _semaphore(available_gb=1.0)

    # Occupy the machine with a task that does fit.
    small = await asyncio.wait_for(sem.acquire(model="small", task_type="summary"), timeout=10.0)

    oversized = asyncio.create_task(sem.acquire(model="enormous-model", task_type="synthesis", response_tokens=100_000))
    await asyncio.sleep(0.3)
    assert not oversized.done(), "an oversized task started while the machine was busy"

    sem.release(small)

    allocation_id = await asyncio.wait_for(oversized, timeout=10.0)
    assert allocation_id
    sem.release(allocation_id)


@pytest.mark.asyncio
async def test_a_queued_task_gives_up_rather_than_waiting_indefinitely():
    """A bounded wait turns a hang into a diagnosable failure."""
    sem = _semaphore(available_gb=10.0)

    blocker = await asyncio.wait_for(sem.acquire(model="m", task_type="summary"), timeout=10.0)
    # Never released: the second acquire has to give up on its own.
    sem.used_vram_gb = 10.0

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(
            sem.acquire(model="m2", task_type="summary", timeout=0.5),
            timeout=10.0,
        )

    assert blocker
