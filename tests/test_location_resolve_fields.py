from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.LocationResolveDTO import LocationResolveResultDTO
from app.services.internal.geo.location_resolve_fields import (
    _iter_coordinate_candidates,
    resolve_pin_location_fields,
)


class LocationResolveFieldsTest(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_uses_nudge_when_primary_fails(self) -> None:
        client = MagicMock()
        client.resolve_wgs84 = AsyncMock(
            side_effect=[
                None,
                LocationResolveResultDTO(location_id=115, address="경기도 오산시 양산동"),
            ],
        )

        result = await resolve_pin_location_fields(
            client,
            latitude=37.206644,
            longitude=126.995064,
            addr_fallback="경기도 화성시 장조1로 34",
            prefer_addr_fallback=True,
            allow_nudge=True,
        )

        self.assertIsNotNone(result)
        assert result is not None
        location_id, detail_address, _pin_point = result
        self.assertEqual(location_id, 115)
        self.assertEqual(detail_address, "경기도 화성시 장조1로 34")
        self.assertGreaterEqual(client.resolve_wgs84.await_count, 2)

    def test_nudge_candidates_include_original_first(self) -> None:
        candidates = _iter_coordinate_candidates(
            latitude=37.0,
            longitude=127.0,
            allow_nudge=True,
        )
        self.assertEqual(candidates[0], (37.0, 127.0))
        self.assertGreater(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()
