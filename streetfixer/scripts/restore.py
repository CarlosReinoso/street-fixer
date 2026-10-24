"""Load a backup made by `scripts.backup` into the database in MONGODB_URI.

Run: .venv/bin/python -m scripts.restore backups/<timestamp>
Refuses to write into a collection that already has documents, so it never
overwrites live data.
"""

import json
import sys
from pathlib import Path

from bson import json_util
from pymongo.operations import SearchIndexModel

from app.db import get_db

BATCH = 1000


def restore(folder: Path) -> None:
    db = get_db()
    if db is None:
        raise SystemExit("Set MONGODB_URI in .env first")

    manifest = json.loads((folder / "manifest.json").read_text())
    indexes = json_util.loads((folder / "indexes.json").read_text())
    search_indexes = json_util.loads((folder / "search_indexes.json").read_text())

    for name, expected in manifest["counts"].items():
        coll = db[name]
        if coll.estimated_document_count():
            raise SystemExit(f"{name} already has documents: restore into an empty database")
        batch = []
        with open(folder / f"{name}.jsonl") as f:
            for line in f:
                batch.append(json_util.loads(line))
                if len(batch) == BATCH:
                    coll.insert_many(batch)
                    batch = []
        if batch:
            coll.insert_many(batch)
        if not expected:
            db.create_collection(name, check_exists=False)

        for ix in indexes.get(name, []):
            opts = {k: v for k, v in ix.items() if k not in ("key", "v", "ns")}
            coll.create_index(list(ix["key"].items()), **opts)
        for ix in search_indexes.get(name, []):
            coll.create_search_index(SearchIndexModel(definition=ix["definition"], name=ix["name"], type=ix["type"]))
        print(f"{name}: {coll.count_documents({})}/{expected} documents, "
              f"{len(indexes.get(name, []))} indexes, {len(search_indexes.get(name, []))} search indexes")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m scripts.restore backups/<timestamp>")
    restore(Path(sys.argv[1]))
