from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from google.genai import errors as genai_errors

from app.core.config import Settings
from app.services.internal.ai.gemini_key_pool import GeminiKeyPool, init_gemini_key_pool
from app.services.internal.ai.gemini_retry import generate_content_with_retry


class ResolvedGeminiApiKeysTest(unittest.TestCase):
    def test_keys_only(self) -> None:
        settings = Settings(
            GEMINI_API_KEYS="key1,key2,key3",
        )
        self.assertEqual(settings.resolved_gemini_api_keys(), ("key1", "key2", "key3"))

    def test_single_key_fallback(self) -> None:
        settings = Settings(
            GEMINI_API_KEY="only",
        )
        self.assertEqual(settings.resolved_gemini_api_keys(), ("only",))

    def test_keys_take_priority_over_single_key(self) -> None:
        settings = Settings(
            GEMINI_API_KEY="ignored",
            GEMINI_API_KEYS="a,b",
        )
        self.assertEqual(settings.resolved_gemini_api_keys(), ("a", "b"))

    def test_dedupe_preserves_order(self) -> None:
        settings = Settings(
            GEMINI_API_KEYS="a,b,a,c,b",
        )
        self.assertEqual(settings.resolved_gemini_api_keys(), ("a", "b", "c"))


class GeminiKeyPoolTest(unittest.IsolatedAsyncioTestCase):
    async def test_round_robin_three_keys(self) -> None:
        pool = GeminiKeyPool(("k1", "k2", "k3"))
        self.assertTrue(pool.enabled)
        indices = []
        for _ in range(5):
            idx, key, _client = await pool.acquire()
            indices.append(idx)
            self.assertEqual(key, ("k1", "k2", "k3")[idx])
        self.assertEqual(indices, [0, 1, 2, 0, 1])

    async def test_single_key_not_enabled(self) -> None:
        pool = GeminiKeyPool(("only",))
        self.assertFalse(pool.enabled)
        idx, key, _ = await pool.acquire()
        self.assertEqual((idx, key), (0, "only"))

    def test_failover_indices(self) -> None:
        pool = GeminiKeyPool(("a", "b", "c"))
        self.assertEqual(pool.failover_indices(0), [1, 2])
        self.assertEqual(pool.failover_indices(2), [0, 1])

    @patch("app.services.internal.ai.gemini_key_pool.settings")
    def test_init_from_settings_empty(self, mock_settings: MagicMock) -> None:
        mock_settings.resolved_gemini_api_keys.return_value = ()
        self.assertIsNone(init_gemini_key_pool())


class GeminiRetryKeyRotationTest(unittest.IsolatedAsyncioTestCase):
    async def test_failover_uses_second_client_on_429(self) -> None:
        pool = GeminiKeyPool(("key-a", "key-b"))
        client_a = MagicMock()
        client_b = MagicMock()
        pool._clients[0] = client_a
        pool._clients[1] = client_b

        err_429 = genai_errors.ClientError(429, {"error": {"message": "rate"}})
        ok_response = MagicMock()

        client_a.aio.models.generate_content = AsyncMock(side_effect=err_429)
        client_b.aio.models.generate_content = AsyncMock(return_value=ok_response)

        result = await generate_content_with_retry(
            client_a,
            model_name="gemini-2.5-flash",
            contents="hello",
            max_attempts_per_model=1,
            key_pool=pool,
            log_prefix="Test",
        )
        self.assertIs(result, ok_response)
        client_b.aio.models.generate_content.assert_awaited_once()
