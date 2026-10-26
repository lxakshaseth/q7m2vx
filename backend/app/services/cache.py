"""Small bounded asynchronous TTL cache used for successful source responses."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, TypeVar


K = TypeVar("K")
V = TypeVar("V")


@dataclass(slots=True)
class _Entry(Generic[V]):
    value: V
    expires_at: float


class AsyncTTLCache(Generic[K, V]):
    """A process-local LRU/TTL cache with atomic get and set operations."""

    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must not be negative")
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds
        self._items: OrderedDict[K, _Entry[V]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def get(self, key: K) -> V | None:
        async with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= time.monotonic():
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return entry.value

    async def set(self, key: K, value: V) -> None:
        if self._ttl_seconds == 0:
            return
        async with self._lock:
            self._items[key] = _Entry(
                value=value,
                expires_at=time.monotonic() + self._ttl_seconds,
            )
            self._items.move_to_end(key)
            while len(self._items) > self._max_entries:
                self._items.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._items.clear()
