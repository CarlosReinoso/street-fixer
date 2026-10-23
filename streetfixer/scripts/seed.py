"""Load councils (ONS boundaries + repair rules) and category configs into Atlas.

Run: .venv/bin/python -m scripts.seed
"""

import json

from app import config
from app.db import ensure_indexes, get_db


def main() -> None:
    db = get_db()
    if db is None:
        raise SystemExit("Set MONGODB_URI in .env first")

    rules = json.load(open(config.DATA_DIR / "councils.json"))
    geo = json.load(open(config.DATA_DIR / "london_boroughs.geojson"))
    for f in geo["features"]:
        name = f["properties"]["LAD26NM"]
        doc = {
            "_id": name,
            "name": name,
            "ons_code": f["properties"]["LAD26CD"],
            "boundary": f["geometry"],
            "pilot": name in rules["pilot"],
            **rules["default"],
            **rules["overrides"].get(name, {}),
        }
        db.councils.replace_one({"_id": name}, doc, upsert=True)
    print(f"councils: {db.councils.count_documents({})}")

    for cat in json.load(open(config.DATA_DIR / "categories.json")):
        db.categories.replace_one({"_id": cat["_id"]}, cat, upsert=True)
    print(f"categories: {db.categories.count_documents({})}")

    ensure_indexes(db)


if __name__ == "__main__":
    main()
