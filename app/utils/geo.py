from __future__ import annotations

from geoalchemy2.elements import WKTElement


def wkt_point_from_wgs84(*, latitude: float, longitude: float) -> WKTElement:
    """WGS84 Point for PostGIS geometry(Point,4326). WKT order is longitude latitude."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)
