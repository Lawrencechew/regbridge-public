from __future__ import annotations

import asyncio
import pytest

from app.core.capacity import GenerationCapacityExceeded, GenerationLimiter


def test_generation_limiter_rejects_without_queueing_and_releases_slot() -> None:
    async def exercise() -> None:
        limiter = GenerationLimiter(limit=1, retry_after_seconds=7)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold_slot() -> None:
            async with limiter.slot():
                entered.set()
                await release.wait()

        holder = asyncio.create_task(hold_slot())
        await entered.wait()
        assert limiter.active == 1
        with pytest.raises(GenerationCapacityExceeded) as failure:
            async with limiter.slot():
                raise AssertionError("A second generation must not be admitted.")
        assert failure.value.retry_after_seconds == 7
        release.set()
        await holder
        assert limiter.active == 0

        with pytest.raises(RuntimeError, match="generation failed"):
            async with limiter.slot():
                raise RuntimeError("generation failed")
        assert limiter.active == 0

    asyncio.run(exercise())
