"""이미지 해시 캐시 추상화 — Upstash Redis(또는 호환). 테스트는 InMemoryCache 주입."""

from __future__ import annotations

import time
from typing import Any, Protocol


class CacheClient(Protocol):
    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str, ttl_seconds: int) -> None: ...


class RedisCache:
    """redis-py 기반(로컬 redis:// / Upstash rediss:// 동일 인터페이스)."""

    def __init__(self, client: Any) -> None:
        self._client = client

    @classmethod
    def from_url(cls, url: str) -> RedisCache:
        import redis

        return cls(redis.Redis.from_url(url, decode_responses=True))

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        return None if value is None else str(value)

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._client.set(key, value, ex=ttl_seconds)


class InMemoryCache:
    """프로세스 메모리 캐시 — 테스트/로컬용. 단순 TTL 만료 추적."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        value, expires_at = item
        if expires_at is not None and time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: str, ttl_seconds: int) -> None:
        expires_at = time.monotonic() + ttl_seconds if ttl_seconds > 0 else None
        self._store[key] = (value, expires_at)
