from __future__ import annotations

from geoalchemy2.elements import WKTElement

from app.schemas.LocationResolveDTO import LocationResolveResultDTO
from app.services.internal.geo.LocationResolveClient import LocationResolveClient
from app.utils.geo import wkt_point_from_wgs84

# 역지오코딩 404(법정동 미매칭) 시 인근 격자 탐색 — 공원·신규 필지 등
_NUDGE_STEPS: tuple[float, ...] = (0.001, 0.005, 0.01, 0.02, 0.05, 0.1)


async def resolve_pin_location_fields(
    client: LocationResolveClient,
    *,
    latitude: float,
    longitude: float,
    addr_fallback: str = "",
    prefer_addr_fallback: bool = False,
    allow_nudge: bool = False,
) -> tuple[int, str, WKTElement] | None:
    """Spring `/api/location/resolve`로 location_id·주소·pin_point를 해석한다."""
    for lat, lng in _iter_coordinate_candidates(
        latitude=latitude,
        longitude=longitude,
        allow_nudge=allow_nudge,
    ):
        resolved = await client.resolve_wgs84(latitude=lat, longitude=lng)
        if resolved is None:
            continue

        location_id = resolved.location_id
        if location_id is None:
            continue

        detail_address = _pick_detail_address(
            resolved,
            addr_fallback,
            prefer_fallback=prefer_addr_fallback,
        )
        if not detail_address:
            continue

        pin_point = wkt_point_from_wgs84(latitude=latitude, longitude=longitude)
        return location_id, detail_address[:150], pin_point

    return None


def _iter_coordinate_candidates(
    *,
    latitude: float,
    longitude: float,
    allow_nudge: bool,
) -> list[tuple[float, float]]:
    candidates: list[tuple[float, float]] = [(latitude, longitude)]
    if not allow_nudge:
        return candidates

    seen = {(_round_coord(latitude), _round_coord(longitude))}
    for step in _NUDGE_STEPS:
        for dlat in (-step, 0.0, step):
            for dlng in (-step, 0.0, step):
                if dlat == 0.0 and dlng == 0.0:
                    continue
                lat = latitude + dlat
                lng = longitude + dlng
                key = (_round_coord(lat), _round_coord(lng))
                if key in seen:
                    continue
                seen.add(key)
                candidates.append((lat, lng))
    return candidates


def _round_coord(value: float) -> float:
    return round(value, 6)


def _pick_detail_address(
    resolved: LocationResolveResultDTO,
    addr_fallback: str,
    *,
    prefer_fallback: bool = False,
) -> str:
    fallback = (addr_fallback or "").strip()
    if prefer_fallback and fallback:
        return fallback
    from_spring = (resolved.address or "").strip()
    if from_spring:
        return from_spring
    return fallback
