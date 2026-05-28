from __future__ import annotations

from geoalchemy2.elements import WKBElement, WKTElement
from geoalchemy2.shape import to_shape


def wkt_point_from_wgs84(*, latitude: float, longitude: float) -> WKTElement:
    """WGS84 Point for PostGIS geometry(Point,4326). WKT order is longitude latitude."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def wgs84_from_pin_point(pin_point: WKBElement) -> tuple[float, float]:
    """geometry(Point,4326) → (latitude, longitude)."""
    point = to_shape(pin_point)
    return float(point.y), float(point.x)


def user_gps_from_wgs84(*, latitude: float, longitude: float) -> str:
    return f"{latitude:.6f},{longitude:.6f}"
