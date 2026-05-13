from __future__ import annotations

import logging
from typing import Any

import httpx

from app.schemas.LocationResolveDTO import LocationResolveResultDTO

logger = logging.getLogger(__name__)


class LocationResolveClient:
    """코어 베이스 URL 기준 좌표 → `location_id`·주소(도로명 등) 해석."""

    _RESOLVE_PATH = "/api/location/resolve"

    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient,
        base_url: str | None,
    ) -> None:
        self._http = http_client
        self._base_url = (base_url or "").strip().rstrip("/") or ""

    async def resolve_wgs84(self, latitude: float, longitude: float) -> LocationResolveResultDTO | None:
        if not self._base_url:
            return None

        url = f"{self._base_url}{self._RESOLVE_PATH}"
        params = {"lat": latitude, "lng": longitude}

        try:
            response = await self._http.get(url, params=params)
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "location resolve HTTP error: %s %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            return None
        except Exception:
            logger.exception("location resolve request failed")
            return None

        if payload.get("isSuccess") is False:
            logger.info(
                "location resolve reported failure: %s — %s",
                payload.get("code"),
                payload.get("message"),
            )
            return None

        raw_result = payload.get("result")
        if raw_result is None and isinstance(payload.get("locationId"), int):
            raw_result = payload

        if not isinstance(raw_result, dict):
            return None

        try:
            return LocationResolveResultDTO.model_validate(raw_result)
        except Exception:
            logger.warning("location resolve result shape unexpected: %s", raw_result)
            return None
