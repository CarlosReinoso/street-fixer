"""Central configuration for Street Fixer.

Every tunable value (model names, distances, database names) lives here so it
can be changed in one place. Secrets come from `.env` in this folder, falling
back to the parent folder's `.env`; they are never hard-coded.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
load_dotenv(ROOT.parent / ".env")  # does not override values already set

# Secrets
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MONGODB_URI = os.getenv("MONGODB_URI", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")

# Models
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-flash-latest")
GEMINI_RETRIES = 3

# Database
DB_NAME = os.getenv("DB_NAME", "streetfixer")

# Filing: "test" never contacts a council (reports are tagged test=True and can be purged).
# Only switch to "live" deliberately, once filing to FixMyStreet/Open311 exists and has been checked.
FILING_MODE = os.getenv("FILING_MODE", "test")
TEST_MODE = FILING_MODE != "live"

# Pipeline
DEDUPE_RADIUS_M = 30          # reports closer than this may be the same problem
MAX_PHOTO_BYTES = 8 * 1024 * 1024
AREA_CACHE_SECONDS = 15      # server + browser cache for map pins in an area

DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "app" / "static"
LOG_DIR = ROOT / "logs"
