"""Who owns this spot? Map a GPS point to the responsible London council.

Online: a `$geoIntersects` query on council boundary polygons in Atlas.
Offline: the same answer from the local ONS GeoJSON with a point-in-polygon test.
"""

import json
from functools import lru_cache

from app import config
from app.db import get_db


@lru_cache
def _local_boundaries() -> list[tuple[str, list]]:
    data = json.load(open(config.DATA_DIR / "london_boroughs.geojson"))
    out = []
    for f in data["features"]:
        geom = f["geometry"]
        polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
        out.append((f["properties"]["LAD26NM"], polys))
    return out


def _in_ring(lon: float, lat: float, ring: list) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _local_lookup(lon: float, lat: float) -> str | None:
    for name, polys in _local_boundaries():
        for poly in polys:
            if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, hole) for hole in poly[1:]):
                return name
    return None


def find_council(lon: float, lat: float) -> dict | None:
    """Return the council doc (name + rules) for a point, or None outside London."""
    db = get_db()
    if db is not None:
        point = {"type": "Point", "coordinates": [lon, lat]}
        return db.councils.find_one({"boundary": {"$geoIntersects": {"$geometry": point}}}, {"boundary": 0})
    name = _local_lookup(lon, lat)
    if name is None:
        return None
    rules = json.load(open(config.DATA_DIR / "councils.json"))
    return {"_id": name, "name": name, **rules["default"], **rules["overrides"].get(name, {})}
