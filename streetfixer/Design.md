# Street Fixer: design

Snap a pothole, fly-tip or broken streetlight. An AI agent sizes it, checks whether it's already reported,
routes it to the right London council and chases it until it's fixed.

## Channels
- **Web page** (`/`): reached by QR sticker or short link. Camera → GPS + draggable pin → reply card.
- **Telegram bot**: same pipeline; instant acknowledgement, message edited as each step finishes. *(Saturday)*
- **Council dashboard** (`/dashboard`): map + risk-ranked queue. *(Saturday)*
- **Tracking page** (`/r/{ref}`): status, timeline, photos, evidence pack. *(Saturday)*

## Pipeline (`app/pipeline.py`)
1. **Classify** (`app/gemini.py`): Gemini vision → strict JSON (`Classification`): category, confidence, summary,
   per-category details (pothole width/depth/surface, fly-tip load size/items/hazards, lamp column ID/fault).
   Sizes are always estimates; reference objects (coin, shoe, finger, kerb) give scale.
2. **Route** (`app/routing.py`): `$geoIntersects` on ONS borough boundaries in Atlas (offline: local point-in-polygon).
3. **Severity**: estimate compared with that council's own repair threshold (`data/councils.json`).
4. **Dedupe**: `$geoNear` (same category, open, ≤30 m); streetlights match on column ID.
   *Next:* hybrid `$rankFusion` (Atlas Search + Vector Search on auto-embedded summaries) + Voyage rerank + Gemini check.
5. **Save**: new issue, or add the report to the existing issue (`report_count`, timeline, max risk).
6. **Reply**: plain English, "estimated", confidence, council rule, report number, tracking link.

## Data (MongoDB Atlas, db `streetfixer`)
| Collection | Doc | Notes |
|---|---|---|
| `councils` | `_id` = borough name, `boundary` (GeoJSON), thresholds, category names | 2dsphere; taxonomic memory |
| `categories` | `_id` = category, fields, size scale, risk weights | config, not code |
| `issues` | one per real problem: `ref`, `category`, `status`, `location`, `council`, `summary`, `details`, `severity`, `risk`, `report_count`, `timeline` | 2dsphere; search/vector indexes on `summary` |
| `reports` | each photo: `issue_id`, `photo`, `location`, `channel`, `classification` | |
| `agent_memory` | Hermes state / short-term / long-term | |

## Atlas features (bounty checklist)
- [x] Geospatial (`$geoIntersects`, `$geoNear`)
- [ ] Automated Embedding on `issues.summary`
- [ ] Atlas Search + Vector Search + Hybrid `$rankFusion`
- [ ] Voyage AI rerank (dedupe) / multimodal photo embeddings
- [ ] Change streams / Stream Processing → live dashboard
- [ ] Agent memory for Hermes

## Config and logging
- All tunables in `app/config.py`; secrets only in `.env` (git-ignored).
- Every Gemini call is logged to `logs/genai.jsonl` (model, prompt, config, output, ms; no image bytes).
- Gemini calls retry with backoff and fall back to `gemini-flash-latest`.

## Run
```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in keys
.venv/bin/python -m scripts.seed   # needs MONGODB_URI
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
