"""Logging helpers.

Every GenAI call is written to `logs/genai.jsonl` (model, prompt, config,
output, timing) with inline image bytes stripped, as the DeepMind hackathon
guide recommends. This makes demo debugging and prompt tuning easy.
"""

import json
import logging
import time
from typing import Any

from app.config import LOG_DIR

LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("streetfixer")


def log_genai(model: str, prompt: str, config: dict, output: Any, started: float, error: str | None = None) -> None:
    """Append one GenAI call record to logs/genai.jsonl (no image bytes)."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": model,
        "prompt": prompt,
        "config": config,
        "output": output,
        "ms": round((time.time() - started) * 1000),
        "error": error,
    }
    with open(LOG_DIR / "genai.jsonl", "a") as f:
        f.write(json.dumps(record, default=str) + "\n")
    log.info("genai %s %sms%s", model, record["ms"], f" ERROR {error}" if error else "")
