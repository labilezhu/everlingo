"""LRU + TTL 缓存，零外部依赖。"""

from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    def __init__(self, maxsize: int = 128, ttl: float = 60):
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._maxsize = maxsize
        self._ttl = ttl

    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        expires, value = self._cache[key]
        if time.monotonic() > expires:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value

    def set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic() + self._ttl, value)
        self._cache.move_to_end(key)
        while len(self._cache) > self._maxsize:
            self._cache.popitem(last=False)

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def clear(self) -> None:
        self._cache.clear()

    async def get_or_set(self, key: str, factory: Callable[[], Any]) -> Any:
        existing = self.get(key)
        if existing is not None:
            return existing
        value = await factory()
        self.set(key, value)
        return value
