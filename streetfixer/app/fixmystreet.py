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

Backup: every successful fetch is upserted into the `fms_reports` collection (one doc per
report, GeoJSON point). When FixMyStreet is down or too slow, pins come from there instead.
Reports no longer in FixMyStreet's open list for a box are marked open=False, not deleted.
"""

import re
import threading
import time
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import httpx
from pymongo import ASCENDING, GEOSPHERE, UpdateOne

from app import config
from app.db import get_db
from app.log import log

FEED = "https://www.fixmystreet.com/rss/l/{lat:.4f},{lon:.4f}/{km}"
AROUND = "https://www.fixmystreet.com/around?ajax=1&bbox={w:.4f},{s:.4f},{e:.4f},{n:.4f}&status=open"
REPORT = "https://www.fixmystreet.com/report/{id}"
NS = {"georss": "http://www.georss.org/georss"}
_cache: dict[tuple, tuple[float, list]] = {}
# FixMyStreet can take 20-40 s when busy: wait for it, but only a couple of requests at a time.
_client = httpx.Client(timeout=config.FMS_TIMEOUT_SECONDS, headers={"User-Agent": config.HTTP_USER_AGENT})
_slots = threading.Semaphore(2)


def _get(url: str, timeout: float | None = None) -> httpx.Response:
    with _slots:
        resp = _client.get(url, timeout=timeout or config.FMS_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp


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


def reports_in(w: float, s: float, e: float, n: float) -> list[dict] | None:
    """Open FixMyStreet reports inside a bounding box, as map pins (cached).

    None means FixMyStreet failed and nothing is cached, so the caller can retry later."""
    key = ("box", round(w, 3), round(s, 3), round(e, 3), round(n, 3))
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.FMS_CACHE_SECONDS:
        return hit[1]
    try:
        raw = _get(AROUND.format(w=w, s=s, e=e, n=n)).json()["pins"]
    except Exception as err:  # not `e`: that is the box's east edge
        log.warning("fixmystreet around failed: %s", err)
        return hit[1] if hit else _from_backup(w, s, e, n)

    detail = {p["ref"]: p for p in reports_near((s + n) / 2, (w + e) / 2, km=1)}
    pins = []
    for lat, lon, _colour, rid, title, *_ in raw:
        ref = f"fms-{rid}"
        pins.append(detail.get(ref) or {
            "ref": ref, "src": "fms", "cat": _category(title), "sev": None, "n": 1,
            "s": title[:120], "ll": [lat, lon], "date": "", "url": REPORT.format(id=rid), "photo": None,
        })
    _cache[key] = (time.time(), pins)
    _save_backup(w, s, e, n, pins)
    return pins


def _box(w: float, s: float, e: float, n: float) -> dict:
    return {"$geoWithin": {"$geometry": {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}}}


_indexed = False


def _save_backup(w: float, s: float, e: float, n: float, pins: list[dict]) -> None:
    """Upsert this box's open reports into Atlas; mark ones that left the open list as closed."""
    global _indexed
    db = get_db()
    if db is None:
        return
    try:
        if not _indexed:
            db.fms_reports.create_index([("ref", ASCENDING)], unique=True)
            db.fms_reports.create_index([("location", GEOSPHERE)])
            _indexed = True
        now = time.time()
        ops = []
        for p in pins:
            doc = {k: v for k, v in p.items() if k != "ll" and v not in (None, "")}  # keep older photo/date if this fetch lacks them
            doc |= {"location": {"type": "Point", "coordinates": p["ll"][::-1]}, "open": True, "seen_at": now}
            ops.append(UpdateOne({"ref": p["ref"]}, {"$set": doc}, upsert=True))
        if ops:
            db.fms_reports.bulk_write(ops, ordered=False)
        db.fms_reports.update_many({"location": _box(w, s, e, n), "open": True, "ref": {"$nin": [p["ref"] for p in pins]}},
                                   {"$set": {"open": False, "closed_seen_at": now}})
    except Exception as ex:
        log.warning("fixmystreet backup save failed: %s", ex)


def _from_backup(w: float, s: float, e: float, n: float) -> list[dict] | None:
    """Open reports for a box from the Atlas backup, or None if there is no backup to use."""
    db = get_db()
    if db is None:
        return None
    try:
        docs = list(db.fms_reports.find({"location": _box(w, s, e, n), "open": True}, {"_id": 0}).limit(300))
    except Exception as ex:
        log.warning("fixmystreet backup read failed: %s", ex)
        return None
    pins = []
    for d in docs:
        d["ll"] = d.pop("location")["coordinates"][::-1]
        for k in ("open", "seen_at", "closed_seen_at"):
            d.pop(k, None)
        pins.append({"sev": None, "n": 1, "date": "", "photo": None} | d)
    log.info("fixmystreet down: %d pins from Atlas backup", len(pins))
    return pins


def reports_near(lat: float, lon: float, km: int = 1) -> list[dict]:
    """Recent FixMyStreet reports within `km` of a point from the RSS feed (cached).

    Open and fixed alike; used to add dates and photos to pins from reports_in."""
    key = (round(lat, 3), round(lon, 3), km)
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < config.FMS_CACHE_SECONDS:
        return hit[1]
    try:
        root = ET.fromstring(_get(FEED.format(lat=lat, lon=lon, km=km), timeout=8).content)
    except Exception as e:
        log.warning("fixmystreet feed failed: %s", e)  # only dates/photos are lost: pins still show
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
