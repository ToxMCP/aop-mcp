"""Simple cache abstraction with in-memory implementation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Optional


@dataclass
class CacheEntry:
    value: Any
    expires_at: Optional[datetime]

    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.utcnow() >= self.expires_at


class Cache:
    def get(self, key: str) -> Any | None:
        raise NotImplementedError

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        raise NotImplementedError


class InMemoryCache(Cache):
    def __init__(self) -> None:
        self._entries: Dict[str, CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.is_expired():
            del self._entries[key]
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        expires = (
            datetime.utcnow() + timedelta(seconds=ttl_seconds)
            if ttl_seconds is not None
            else None
        )
        self._entries[key] = CacheEntry(value=value, expires_at=expires)

