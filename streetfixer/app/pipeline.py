"""The report pipeline shared by every channel (web page, Telegram bot).

photo + location
  -> classify (Gemini vision)
  -> route (which council owns this spot)
  -> severity (compare the estimate with that council's repair threshold)
  -> dedupe ($geoNear: same category, open, within DEDUPE_RADIUS_M)
  -> save (new issue, or add the report to the existing one)
  -> reply (plain-English message for the reporter)
"""

import secrets
import uuid
from datetime import datetime, timezone

from app import config
from app.db import get_db
from app.gemini import Classification, classify_photo
from app.log import log
from app.routing import find_council

UPLOAD_DIR = config.ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

LABELS = {"pothole": "Pothole", "fly_tipping": "Fly-tipping", "streetlight": "Streetlight", "other": "Street problem"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def assess_severity(c: Classification, council: dict | None) -> tuple[str, float, str | None]:
    """Return (severity, risk score 0-10, explanation) using the council's own rules."""
    if c.category == "pothole" and c.pothole and c.pothole.depth_mm:
        surface = c.pothole.surface if c.pothole.surface != "unknown" else "road"
        threshold = (council or {}).get("pothole_threshold_mm", {}).get(surface, 40)
        depth = c.pothole.depth_mm
        risk = min(10.0, depth / threshold * 5 * (1.5 if surface == "cycle_lane" else 1))
        who = (council or {}).get("name", "The council")
        if depth >= threshold:
            return "urgent", round(risk, 1), f"{who} repairs {surface.replace('_', ' ')} potholes from {threshold} mm"
        return "standard", round(risk, 1), f"below {who}'s {threshold} mm repair level for now, we'll keep watching it"
    if c.category == "fly_tipping" and c.fly_tipping:
        if c.fly_tipping.hazards:
            return "urgent", 9.0, "hazardous waste: please don't touch it"
        scale = ["bag", "car_boot", "small_van", "transit_van", "tipper_lorry"]
        size = scale.index(c.fly_tipping.size) if c.fly_tipping.size in scale else 1
        return ("urgent" if size >= 3 else "standard"), round(3 + size * 1.5, 1), None
    if c.category == "streetlight":
        return "standard", 5.0, None
    return "standard", 3.0, None


def find_duplicate(db, c: Classification, lon: float, lat: float) -> dict | None:
    """Find an open issue that is probably the same problem.

    Step 1 (here): $geoNear on open issues of the same category within the radius.
    Streetlights match exactly on the lamp column ID when Gemini could read it.
    """
    if c.category == "streetlight" and c.streetlight and c.streetlight.column_id:
        hit = db.issues.find_one({"category": "streetlight", "status": {"$ne": "fixed"},
                                  "details.column_id": c.streetlight.column_id})
        if hit:
            return hit
    pipeline = [
        {"$geoNear": {
            "near": {"type": "Point", "coordinates": [lon, lat]},
            "distanceField": "distance_m",
            "maxDistance": config.DEDUPE_RADIUS_M,
            "query": {"category": c.category, "status": {"$ne": "fixed"}},
            "spherical": True,
        }},
        {"$limit": 1},
    ]
    return next(db.issues.aggregate(pipeline), None)


def _details(c: Classification) -> dict:
    sub = getattr(c, c.category, None) if c.category in ("pothole", "fly_tipping", "streetlight") else None
    return sub.model_dump() if sub else {}


def build_reply(c: Classification, council: dict | None, severity: str, why: str | None, count: int, ref: str | None) -> str:
    """The message the reporter sees. Sizes are always labelled as estimates."""
    if c.category == "not_a_street_problem":
        return "I couldn't see a street problem in that photo. Try again closer, with the problem in the middle."
    lines = []
    label = LABELS.get(c.category, "Street problem")
    if c.category == "pothole" and c.pothole:
        dims = []
        if c.pothole.width_cm:
            dims.append(f"~{c.pothole.width_cm:.0f} cm wide")
        if c.pothole.depth_mm:
            dims.append(f"~{c.pothole.depth_mm:.0f} mm deep")
        lines.append(f"{label}: estimated {', '.join(dims) or 'size unclear'} ({c.confidence} confidence).")
    elif c.category == "fly_tipping" and c.fly_tipping:
        size = (c.fly_tipping.size or "unknown size").replace("_", " ")
        items = ", ".join(c.fly_tipping.items[:3])
        lines.append(f"{label}: about a {size} load{f' ({items})' if items else ''}.")
        if c.fly_tipping.hazards:
            lines.append(f"⚠️ Possible {', '.join(c.fly_tipping.hazards)}. Please don't touch it.")
    elif c.category == "streetlight" and c.streetlight:
        cid = f" (lamp {c.streetlight.column_id})" if c.streetlight.column_id else ""
        lines.append(f"{label}{cid}: {c.streetlight.fault.replace('_', ' ')}.")
    else:
        lines.append(c.summary)

    if council is None:
        lines.append("This spot looks outside London's boroughs, so I can't route it yet.")
    else:
        lines.append(f"{council['name']}: {why + ', ' if why else ''}marked {severity}.")
    if count > 1:
        lines.append(f"You're report #{count} for this problem. I've added your photo to it.")
    elif ref:
        lines.append("First report here. I'll file it and chase it.")
    if c.needs_reference:
        lines.append("Tip: a coin or your shoe next to it helps me measure it.")
    if ref and config.TEST_MODE:
        lines.append("🧪 Test mode: saved, but not sent to the council.")
    if ref:
        lines.append(f"Track it: /r/{ref}")
    return "\n".join(lines)


def process_report(photo: bytes, mime_type: str, lon: float, lat: float, channel: str,
                   note: str | None = None, contact: str | None = None) -> dict:
    """Run the full pipeline for one photo and return a result dict for the UI."""
    c = classify_photo(photo, mime_type, note)
    council = find_council(lon, lat)
    severity, risk, why = assess_severity(c, council)

    if c.category == "not_a_street_problem":
        return {"classification": c.model_dump(), "council": None, "reply": build_reply(c, None, severity, why, 0, None)}

    photo_name = f"{uuid.uuid4().hex}.{'png' if 'png' in mime_type else 'jpg'}"
    (UPLOAD_DIR / photo_name).write_bytes(photo)

    db = get_db()
    ref, count, issue_id, duplicate = None, 1, None, False
    if db is not None:
        now = _now()
        point = {"type": "Point", "coordinates": [lon, lat]}
        dup = find_duplicate(db, c, lon, lat)
        report = {"_id": uuid.uuid4().hex, "photo": photo_name, "location": point, "channel": channel,
                  "classification": c.model_dump(), "note": note, "contact": contact, "created_at": now,
                  "test": config.TEST_MODE}
        if dup:
            duplicate = True
            issue_id, ref = dup["_id"], dup["ref"]
            updated = db.issues.find_one_and_update(
                {"_id": issue_id},
                {"$inc": {"report_count": 1},
                 "$set": {"last_reported": now},
                 "$max": {"risk": risk},
                 "$push": {"timeline": {"at": now, "event": "report", "note": f"New report via {channel}"}}},
                return_document=True)
            count = updated["report_count"]
            if severity == "urgent" and dup.get("severity") != "urgent":
                db.issues.update_one({"_id": issue_id}, {"$set": {"severity": "urgent"}})
        else:
            issue_id, ref = uuid.uuid4().hex, secrets.token_urlsafe(4)
            filing_note = (f"TEST MODE: would file with {council['name'] if council else 'the council'} "
                           f"via {council.get('channel', 'FixMyStreet') if council else 'FixMyStreet'}, not sent")
            db.issues.insert_one({
                "_id": issue_id, "ref": ref, "category": c.category, "status": "open", "test": config.TEST_MODE,
                "location": point, "council": council["name"] if council else None,
                "summary": c.summary, "location_hint": c.location_hint, "details": _details(c),
                "severity": severity, "risk": risk, "confidence": c.confidence,
                "report_count": 1, "first_reported": now, "last_reported": now, "cover_photo": photo_name,
                "timeline": [{"at": now, "event": "report", "note": f"First report via {channel}"}]
                            + ([{"at": now, "event": "filing_skipped", "note": filing_note}] if config.TEST_MODE else []),
            })
        report["issue_id"] = issue_id
        db.reports.insert_one(report)
    else:
        log.info("offline mode: report not saved")

    return {
        "classification": c.model_dump(), "council": council["name"] if council else None,
        "severity": severity, "risk": risk, "why": why, "ref": ref, "issue_id": issue_id,
        "duplicate": duplicate, "report_count": count, "photo": photo_name,
        "reply": build_reply(c, council, severity, why, count, ref),
    }
