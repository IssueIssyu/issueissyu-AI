from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from google import genai

from app.core.config import settings

if TYPE_CHECKING:
    pass

_pool: GeminiKeyPool | None = None


def mask_api_key(api_key: str) -> str:
    key = (api_key or "").strip()
    if len(key) <= 8:
        return "***"
    return f"...{key[-4:]}"


class GeminiKeyPool:
    def __init__(self, api_keys: tuple[str, ...]) -> None:
        if not api_keys:
            raise ValueError("GeminiKeyPool requires at least one API key")
        self._api_keys = api_keys
        self._index = 0
        self._lock = threading.Lock()
        self._clients: dict[int, genai.Client] = {}

    @classmethod
    def from_settings(cls) -> GeminiKeyPool:
        keys = settings.resolved_gemini_api_keys()
        if not keys:
            raise ValueError("No Gemini API keys configured")
        return cls(keys)

    @property
    def size(self) -> int:
        return len(self._api_keys)

    @property
    def enabled(self) -> bool:
        return self.size >= 2

    def primary_api_key(self) -> str:
        return self._api_keys[0]

    def api_key_at(self, index: int) -> str:
        if index < 0 or index >= self.size:
            raise IndexError(f"Gemini key index out of range: {index}")
        return self._api_keys[index]

    def _advance_index(self) -> int:
        with self._lock:
            idx = self._index
            self._index = (idx + 1) % self.size
            return idx

    def client_at(self, index: int) -> genai.Client:
        if index < 0 or index >= self.size:
            raise IndexError(f"Gemini key index out of range: {index}")
        client = self._clients.get(index)
        if client is None:
            client = genai.Client(api_key=self._api_keys[index])
            self._clients[index] = client
        return client

    async def acquire(self) -> tuple[int, str, genai.Client]:
        idx = self._advance_index()
        api_key = self._api_keys[idx]
        return idx, api_key, self.client_at(idx)

    def acquire_sync(self) -> tuple[int, str, genai.Client]:
        idx = self._advance_index()
        api_key = self._api_keys[idx]
        return idx, api_key, self.client_at(idx)

    def failover_indices(self, start_index: int) -> list[int]:
        if self.size <= 1:
            return []
        return [(start_index + offset) % self.size for offset in range(1, self.size)]


def init_gemini_key_pool() -> GeminiKeyPool | None:
    global _pool
    keys = settings.resolved_gemini_api_keys()
    if not keys:
        _pool = None
        return None
    _pool = GeminiKeyPool(keys)
    return _pool


def get_gemini_key_pool() -> GeminiKeyPool | None:
    global _pool
    if _pool is None:
        return init_gemini_key_pool()
    return _pool
