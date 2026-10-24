"""Existing public reports from FixMyStreet (mySociety), for the map.

Two public sources, read for one map grid cell at a time and cached for
FMS_CACHE_SECONDS so we never hammer their service:
  https://www.fixmystreet.com/around?ajax=1&bbox={w},{s},{e},{n}&status=open
    the JSON behind their own map: every open report in the box, including ones
    passed to other bodies such as TfL Streetcare. This is the list of pins.
  https://www.fixmystreet.com/rss/l/{lat},{lon}/{km}
    GeoRSS with dates and photos, but it leaves out reports sent to TfL and
    includes fixed ones, so it only adds detail to pins from the first source.
Pins use the same light format as our own issues and link back to the original report.
"""

import re
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx

from app import config
from app.log import log

FEED = "https://www.fixmystreet.com/rss/l/{lat:.4f},{lon:.4f}/{km}"
AROUND = "https://www.fixmystreet.com/around?ajax=1&bbox={w:.4f},{s:.4f},{e:.4f},{n:.4f}&status=open"
REPORT = "https://www.fixmystreet.com/report/{id}"
NS = {"georss": "http://www.georss.org/georss"}
_cache: dict[tuple, tuple[float, list]] = {}
_client = httpx.Client(timeout=8, headers={"User-Agent": config.HTTP_USER_AGENT})


def _category(text: str) -> str:
    t = text.lower()
    if "pothole" in t or "road surface" in t or "carriageway" in t:
        return "pothole"
    if "fly" in t and "tip" in t:
        return "fly_tipping"
    if "light" in t or "lamp" in t:
        return "streetlight"
    return "other"


def _photo(description: str) -> str | None:
    m = re.search(r'<img src="([^"]+)"', description or "")
    return m.group(1) if m else None


def reports_in(w: float, s: float, e: float, n: float) -> list[dict]:
    """Open FixMyStreet reports inside a bounding box, as map pins (cached)."""
    key = ("box", round(w, 3), round(s, 3), round(e, 3), round(n, 3))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.FMS_CACHE_SECONDS:
        return hit[1]
    try:
        resp = _client.get(AROUND.format(w=w, s=s, e=e, n=n))
        resp.raise_for_status()
        raw = resp.json()["pins"]
    except Exception as e:
        log.warning("fixmystreet around failed: %s", e)
        return hit[1] if hit else []

    detail = {p["ref"]: p for p in reports_near((s + n) / 2, (w + e) / 2, km=1)}
    pins = []
    for lat, lon, _colour, rid, title, *_ in raw:
        ref = f"fms-{rid}"
        pins.append(detail.get(ref) or {
            "ref": ref, "src": "fms", "cat": _category(title), "sev": None, "n": 1,
            "s": title[:120], "ll": [lat, lon], "date": "", "url": REPORT.format(id=rid), "photo": None,
        })
    _cache[key] = (time.time(), pins)
    return pins


def reports_near(lat: float, lon: float, km: int = 1) -> list[dict]:
    """Recent FixMyStreet reports within `km` of a point from the RSS feed (cached).

    Open and fixed alike; used to add dates and photos to pins from reports_in."""
    key = (round(lat, 3), round(lon, 3), km)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.FMS_CACHE_SECONDS:
        return hit[1]
    try:
        resp = _client.get(FEED.format(lat=lat, lon=lon, km=km))
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception as e:
        log.warning("fixmystreet feed failed: %s", e)
        return hit[1] if hit else []

    pins = []
    for item in root.iter("item"):
        point = item.findtext("georss:point", namespaces=NS)
        link = item.findtext("link") or ""
        if not point or "/report/" not in link:
            continue
        plat, plon = (float(v) for v in point.split())
        cat_text = item.findtext("category") or item.findtext("title") or ""
        try:
            date = parsedate_to_datetime(item.findtext("pubDate")).strftime("%d %b")
        except Exception:
            date = ""
        pins.append({
            "ref": "fms-" + link.rsplit("/", 1)[-1],
            "src": "fms",
            "cat": _category(cat_text),
            "sev": None,
            "n": 1,
            "s": f"{item.findtext('title') or ''} · {cat_text}".strip(" ·")[:120],
            "ll": [plat, plon],
            "date": date,
            "url": link,
            "photo": _photo(item.findtext("description") or ""),
        })
    _cache[key] = (time.time(), pins)
    return pins
