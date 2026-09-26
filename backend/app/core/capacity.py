from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class GenerationCapacityExceeded(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("Output generation capacity is currently full.")
        self.retry_after_seconds = retry_after_seconds


class GenerationLimiter:
    """Fail-fast per-process admission control for memory-heavy generation work."""

    def __init__(self, limit: int, retry_after_seconds: int) -> None:
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        self._active = 0
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return self._active

    @asynccontextmanager
    async def slot(self) -> AsyncIterator[None]:
        async with self._lock:
            if self._active >= self.limit:
                raise GenerationCapacityExceeded(self.retry_after_seconds)
            self._active += 1
        try:
            yield
        finally:
            async with self._lock:
                self._active -= 1
