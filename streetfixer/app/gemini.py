"""Gemini vision: turn a street photo into a structured problem report.

`classify_photo` sends the photo to Gemini with a strict JSON schema and
returns a `Classification`. It retries on transient errors (503/500, "model
overloaded") and falls back to a second model, then logs every call.
"""

import time
from typing import Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app import config
from app.log import log, log_genai

_client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None


class Pothole(BaseModel):
    width_cm: float | None = Field(None, description="Estimated widest dimension in cm")
    depth_mm: float | None = Field(None, description="Estimated deepest point in mm")
    surface: Literal["road", "pavement", "cycle_lane", "unknown"] = "unknown"


class FlyTipping(BaseModel):
    size: Literal["bag", "car_boot", "small_van", "transit_van", "tipper_lorry"] | None = None
    items: list[str] = Field(default_factory=list, description="Main items, e.g. mattress, sofa, rubble bags")
    hazards: list[str] = Field(default_factory=list, description="Dangerous items: asbestos, needles, chemicals, gas cylinders, broken glass")


class Streetlight(BaseModel):
    column_id: str | None = Field(None, description="ID painted or stuck on the lamp column, exactly as written")
    fault: Literal["out", "flickering", "day_burning", "damaged", "unknown"] = "unknown"


class Classification(BaseModel):
    category: Literal["pothole", "fly_tipping", "streetlight", "other", "not_a_street_problem"]
    confidence: Literal["low", "medium", "high"]
    summary: str = Field(description="One plain-English sentence describing the problem, for search and for the council")
    reference_object: str | None = Field(None, description="Object used for scale (coin, shoe, finger, kerb, bin), or null")
    needs_reference: bool = Field(description="True if size cannot be estimated without a reference object")
    location_hint: str | None = Field(None, description="Any street name, shop name or landmark readable in the photo")
    pothole: Pothole | None = None
    fly_tipping: FlyTipping | None = None
    streetlight: Streetlight | None = None


PROMPT = """You are Street Fixer's inspector for London street problems.
Look at the photo and fill the JSON schema.

Rules:
- category: pothole, fly_tipping, streetlight (broken/out lamp), other (another street problem), or not_a_street_problem.
- Fill ONLY the sub-object matching the category; leave the others null.
- Sizes are ESTIMATES. Use reference objects to scale: £1 coin 23.4 mm wide, adult shoe ~28 cm, adult finger ~8 cm long
  (nail ~1 cm, 1st knuckle ~2 cm, 2nd knuckle ~4.5 cm), kerb stone ~12-15 cm tall, wheelie bin lid ~58 cm wide,
  road lane ~3 m wide. Name the object you used in reference_object.
- If no reference is visible and size matters, still give your best estimate, set confidence low and needs_reference true.
- surface: road, pavement or cycle_lane (painted cycle markings / blue or green surfacing / segregated lane).
- Fly-tipping size is the load scale: bag, car_boot, small_van, transit_van, tipper_lorry. Flag any hazard you can see.
- Streetlight: copy the column ID exactly as written (letters and numbers). Null if unreadable.
- location_hint: copy any readable street sign, shop name or landmark; do not guess.
- Never invent details you cannot see. Ignore people and number plates; never describe a person.
"""


def _config() -> types.GenerateContentConfig:
    return types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Classification,
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_level="low"),
        media_resolution=types.MediaResolution.MEDIA_RESOLUTION_MEDIUM,
    )


def classify_photo(image: bytes, mime_type: str = "image/jpeg", note: str | None = None) -> Classification:
    """Classify one street photo. `note` is optional text the reporter added."""
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY is not set")
    prompt = PROMPT + (f"\nReporter's note: {note}" if note else "")
    contents = [types.Part.from_bytes(data=image, mime_type=mime_type), prompt]
    cfg = _config()
    cfg_log = {"schema": "Classification", "temperature": 0.2, "thinking_level": "low", "media_resolution": "medium"}

    last_error = None
    for attempt in range(config.GEMINI_RETRIES):
        model = config.GEMINI_MODEL if attempt < config.GEMINI_RETRIES - 1 else config.GEMINI_FALLBACK_MODEL
        started = time.time()
        try:
            resp = _client.models.generate_content(model=model, contents=contents, config=cfg)
            result = resp.parsed if isinstance(resp.parsed, Classification) else Classification.model_validate_json(resp.text)
            log_genai(model, prompt, cfg_log, result.model_dump(), started)
            return result
        except Exception as e:  # transient 5xx / overload: back off and retry
            last_error = e
            log_genai(model, prompt, cfg_log, None, started, error=str(e)[:300])
            time.sleep(0.8 * (attempt + 1))
    log.error("classify_photo failed after retries: %s", last_error)
    raise RuntimeError(f"Gemini failed: {last_error}")
