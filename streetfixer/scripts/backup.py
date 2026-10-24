"""Export the whole Street Fixer database to local files, so the Atlas cluster can be
terminated after the hackathon and restored later with `scripts.restore`.

Writes backups/<UTC timestamp>/:
  <collection>.jsonl    one document per line, MongoDB Extended JSON (keeps types: dates, ids)
  indexes.json          standard index definitions per collection
  search_indexes.json   Atlas Search / Vector Search index definitions per collection
  manifest.json         document counts, checked against the files after writing

Run: .venv/bin/python -m scripts.backup
Prints the backup folder on success; exits non-zero if any count does not match.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from bson import json_util

from app import config
from app.db import get_db

BACKUP_DIR = config.ROOT / "backups"


def backup() -> Path:
    db = get_db()
    if db is None:
        raise SystemExit("Set MONGODB_URI in .env first")

    out = BACKUP_DIR / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True)
    counts, indexes, search_indexes = {}, {}, {}
    for name in sorted(db.list_collection_names()):
        coll = db[name]
        with open(out / f"{name}.jsonl", "w") as f:
            n = 0
            for doc in coll.find():
                f.write(json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS) + "\n")
                n += 1
        counts[name] = n
        indexes[name] = [ix for ix in coll.list_indexes() if ix["name"] != "_id_"]
        try:
            search_indexes[name] = [{"name": ix["name"], "type": ix.get("type", "search"),
                                     "definition": ix["latestDefinition"]} for ix in coll.list_search_indexes()]
        except Exception:  # not supported on this deployment
            search_indexes[name] = []

    (out / "indexes.json").write_text(json_util.dumps(indexes, indent=2))
    (out / "search_indexes.json").write_text(json_util.dumps(search_indexes, indent=2))
    manifest = {"db": config.DB_NAME, "created_at": datetime.now(timezone.utc).isoformat(), "counts": counts}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))

    # Verify: every file has as many lines as the collection had documents.
    for name, n in counts.items():
        lines = sum(1 for _ in open(out / f"{name}.jsonl"))
        if lines != n:
            raise SystemExit(f"backup check failed for {name}: {lines} lines, {n} documents")
    print(out)
    return out


if __name__ == "__main__":
    backup()
