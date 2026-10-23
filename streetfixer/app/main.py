"""Street Fixer web API.

Run: .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

Routes:
  GET  /               mobile reporting page
  GET  /dashboard      council map + risk-ranked queue
  GET  /r/{ref}        tracking page for one issue
  POST /api/report     photo + location -> pipeline result
  GET  /api/issues     open issues for the dashboard
  GET  /api/issues/{ref}
"""

import time

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import config
from app.db import get_db
from app.log import log
from app.pipeline import UPLOAD_DIR, process_report

app = FastAPI(title="Street Fixer")
_area_cache: dict[tuple, tuple[float, list]] = {}  # bbox -> (time, pins)
app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/")
def report_page():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/dashboard")
def dashboard_page():
    return FileResponse(config.STATIC_DIR / "dashboard.html")


@app.get("/r/{ref}")
def track_page(ref: str):
    return FileResponse(config.STATIC_DIR / "track.html")


@app.post("/api/report")
async def api_report(photo: UploadFile = File(...), lat: float = Form(...), lon: float = Form(...),
                     note: str | None = Form(None), contact: str | None = Form(None)):
    data = await photo.read()
    if not data:
        raise HTTPException(400, "Empty photo")
    if len(data) > config.MAX_PHOTO_BYTES:
        raise HTTPException(413, "Photo too large")
    try:
        result = await run_in_threadpool(process_report, data, photo.content_type or "image/jpeg",
                                         lon, lat, "web", note, contact)
        _area_cache.clear()  # new pin: map areas must refresh
        return result
    except RuntimeError as e:
        log.error("report failed: %s", e)
        raise HTTPException(503, "The AI is busy right now. Please try again in a moment.")


def _public(issue: dict) -> dict:
    issue["id"] = issue.pop("_id")
    issue.pop("contact", None)
    return issue


@app.get("/api/mode")
def api_mode():
    return {"test_mode": config.TEST_MODE, "db": get_db() is not None}


@app.get("/api/issues/area")
def api_issues_area(response: Response, w: float, s: float, e: float, n: float):
    """Light map pins for open issues inside a bounding box (one grid cell from the client).

    Returns only what a pin needs; details and photos load later, when a pin is opened.
    Results are cached in memory for a few seconds and the cache is cleared on every new report.
    """
    response.headers["Cache-Control"] = f"public, max-age={config.AREA_CACHE_SECONDS}"
    if e - w > 0.2 or n - s > 0.2:
        raise HTTPException(400, "Area too large")
    db = get_db()
    if db is None:
        return []
    key = (round(w, 4), round(s, 4), round(e, 4), round(n, 4))
    hit = _area_cache.get(key)
    if hit and time.time() - hit[0] < config.AREA_CACHE_SECONDS:
        return hit[1]
    box = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    proj = {"_id": 0, "ref": 1, "category": 1, "severity": 1, "report_count": 1, "summary": 1, "location.coordinates": 1}
    pins = [{"ref": i["ref"], "cat": i["category"], "sev": i.get("severity"), "n": i.get("report_count", 1),
             "s": i.get("summary", "")[:120], "ll": i["location"]["coordinates"][::-1]}
            for i in db.issues.find({"status": {"$ne": "fixed"}, "location": {"$geoWithin": {"$geometry": box}}}, proj).limit(300)]
    _area_cache[key] = (time.time(), pins)
    return pins


@app.get("/api/issues")
def api_issues(council: str | None = None):
    db = get_db()
    if db is None:
        return []
    q = {"status": {"$ne": "fixed"}}
    if council:
        q["council"] = council
    return [_public(i) for i in db.issues.find(q).sort([("severity", -1), ("risk", -1)]).limit(500)]


@app.get("/api/issues/{ref}")
def api_issue(ref: str):
    db = get_db()
    issue = db.issues.find_one({"ref": ref}) if db is not None else None
    if not issue:
        raise HTTPException(404, "Not found")
    issue = _public(issue)
    issue["photos"] = [r["photo"] for r in db.reports.find({"issue_id": issue["id"]}, {"photo": 1}).sort("created_at", 1)]
    return issue
