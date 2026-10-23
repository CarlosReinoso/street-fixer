# Street Fixer: Encode London Hackathon (23–25 Oct 2026)

Snap a pothole, fly-tip or broken streetlight. An AI agent sizes it, checks whether it's already reported,
routes it to the right London council and chases it until it's fixed.

Built on **MongoDB Atlas** (geo, search, vector, agent memory) and **Gemini** vision.

- `streetfixer/`: the app (FastAPI + Gemini + Atlas). See [`streetfixer/Design.md`](streetfixer/Design.md).
- `index.html`: hackathon ideas dashboard.
- `notes.md`: event notes (judges, workshops, bounty rules).
- `streetfixer-cover.*`: project image.

## Run
```
cd streetfixer
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # GEMINI_API_KEY, MONGODB_URI
.venv/bin/python -m scripts.seed
.venv/bin/uvicorn app.main:app --port 8000
```
Reports run in **test mode** by default: nothing is sent to any council.
