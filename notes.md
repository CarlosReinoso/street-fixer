# Encode London Hackathon — 23–25 Oct 2026 (Encode Hub, 41 Pitfield St)

## Facts
- Fri: workshops 14:30–16:30 (Gemini 14:30, Arc/Circle 15:00, MongoDB 15:30, Saint 16:00), teams 16:30, **hacking 17:00**, **check-in 18:00** (idea + bounty + say YES to Saint if going for it — only 10 teams get a Saint agent)
- Sat **18:00 progress**: demo link (placeholder ok) + GitHub + problem statement
- Sun: final submissions + demos + judging, ends 16:30. Overall winners = **audience vote** (Hub membership + Treg $500/$250/$100)
- Tracks: **The Real World** (AI for people/planet) | **Agents That Ship** (real boring job end-to-end, no babysitting) — AirPods + Encode coffee card
- Criteria: Innovation, Technical execution, Impact, Usability. Bounties also score tech usage.
- Bounties: MongoDB Atlas £6,800 (more Atlas features = more points: Vector, Atlas Search, Hybrid, Auto Embedding, Stream Processing, Voyage AI; $100 credit at booth) · DeepMind Gemini 4 Argon $15k API credits · Saint £200 + Saint per member + 3 months · Treg $20 each (treg.to/llms.txt)

## Judges
| Judge | Org | What they care about |
|---|---|---|
| Amit Vadi | Google DeepMind (Head of Community, Gemini API/AI Studio) | real people using Gemini, good dev story |
| Geneviève Huskens | Google DeepMind DevX | demoed Argon building from real-world photos, sub-agents → multimodal |
| Robin Varghese, Maja Brlek, Ricardo Villanueva | MongoDB | Atlas as core store, feature count |
| Daniil Mazepin | CoreWeave (London eng leader, unconfirmed) | solid engineering, AI + engineers |
| Alex Saunders | Flywheel (unclear which one) | — |
| Efe Erciyaz, Sohum Patel | Penelope Health (API for medical codes/docs for claims; $100M raised Sep 2026) | healthcare admin, paperwork automation |
| Samuel Videau | Genius (CTO, on-chain trading terminal) | crypto/payments → pairs with Arc/Circle |
| Timo Beckmann | Droidrun (co-founder; Android/mobile agent framework) | agents operating phones |
| Amgad Al-Zamkan | Tenor (likely heytenor, YC S26: agents as workers with identity + budget) | accountable agents |
| Miles Emami | Advent International (PE, consumer, ex-McKinsey) | business case, who pays |

## 10 ideas — see chat summary; top picks: #2 Tradie back office, #6 Damp & Mould Chaser, #1 Claim Appeal Agent

## MongoDB workshop (Fri 16:00)
- Credit code **MKT-ENCODELDN-100**: account.mongodb.com → choose your Atlas org → Billing → Apply Code
- Slide "MongoDB + Voyage AI": unstructured data → embedding → vector search → **reranker** → LLM, all in one place
- Slide "Agentic AI": Atlas = agent memory: **State / Short-term / Long-term** ("start where we left off", "customer's history"); frameworks LangGraph/CrewAI/Autogen/MCP
- Slide "Automated Embedding": doc auto-embedded, text + vector in one collection, index managed; query in plain English
- New ideas: #11 CareLog (family carer memory), #12 Fix-It Memory (repair RAG over manuals)

## MongoDB talk transcript takeaways
- Prizes £3,500 / £2,000 / £1,300. Qualify = use MongoDB; more features **visibly demonstrated** = more points. Quality of idea/use case first, then build quality; no load testing
- $100 → M30 (8GB dedicated) ~154h → spin up Fri night, pause after Sunday
- "Accurate AI is never a model problem": the moat is the data your users generate
- Auto-embed on write + on query (pass raw text); hybrid + rerankers built in; bring your own embeddings is fine (e.g. Voyage multimodal for photos)
- Memory types: short-term, long-term, taxonomic
- MongoDB agent skills for Claude Code/Cursor/Codex: install them
- Weak spots (per speaker): time series, long analytics queries
- Bank story: ~20 days to open a UK business account, rigid schema → idea #13
- New ideas: #13 Business Account in a Day, #14 Found It (lost & found), #15 Atlas Memory for Hermes

## Street Fixer — pre-empting potholes (proactive detection)
- Don't only wait for reports: spot potholes *before* anyone reports them, from open live streams and existing research.
- **Live / public camera feeds:** TfL JamCams (open data API, ~900 London traffic cameras, refreshed every few minutes) and other public traffic or street webcams. Gemini vision samples frames → flags likely potholes, fly-tips and dead lights → creates "suspected" issues in Atlas, pinned to the camera's location.
- **Street imagery over time:** Mapillary (open, crowdsourced) and dashcam / e-bike / bus fleet footage can be compared over time to catch cracks growing into potholes.
- **Existing research and data to build on (not reinvent):**
  - Public pothole datasets (e.g. RDD2022 road damage dataset, Kaggle pothole sets) and YOLO-style detectors as a cheap first-pass filter before Gemini.
  - Academic work on predicting road deterioration (weather, freeze–thaw, traffic load, road age, past repairs).
  - FixMyStreet open data: historical reports show where problems keep coming back.
- **Use in Street Fixer:** camera detections plus history → risk score per street segment → "likely to fail next" map for councils (the "prediction" step in the vertical scale).
- **MongoDB angle:** Stream Processing on camera frames / detections, time-series collection per segment, vector search over images to match a resident's photo to a camera sighting.
- **Caveats:** check each feed's licence and terms; detections stay "suspected" until a person or council confirms; no faces/plates stored (blur, keep only the crop of the defect).
- Weekend scope: a stretch goal or demo teaser (one JamCam frame → detection) — the core build stays photo reports.

## Google DeepMind temp account (Gemini) — rules (goo.gle/hackathon-account)
- Temporary account (devstar…@gcplab.me, password NOT stored here); **deleted ~1 day after the event**, so export all work and keep code in our own git.
- **Never commit the API key** — a leaked key gets revoked and can break the whole project. Key lives in `.env` (git-ignored) as `GEMINI_API_KEY`. If leaked: delete at aistudio.google.com/api-keys and create a new one (removing it in a later commit is not enough).
- **No heavy use** (thousands of requests) → disqualification + ban. Cache Gemini results per photo, no loops over camera feeds at scale.
- Each teammate should use their own temp account.
- Gives: higher rate limits, paid models (Gemini 3.1 Pro, Veo, Nano-Banana), Cloud Run (also deleted after).
- Setup: new Chrome profile → sign in at AI Studio → aistudio.google.com/api-keys → "Import project" if missing → use the Tier 3 key (or "Create API key").
- Antigravity: NOT the blue OAuth button (free tier); use the small grey link → sign in with temp account → paste project ID from aistudio.google.com/projects → region "global" for 3.1 Pro.
- 503 / "model overwhelmed" → retry with backoff or fall back to an older/Flash model. Keep model names in one config.
- Their recommended habits: one file per feature, docstrings, header comments, `Design.md` at root, log every GenAI call (model, prompt, config, output, no inline image data), git often.
