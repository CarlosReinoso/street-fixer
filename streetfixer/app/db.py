"""MongoDB Atlas access: connection, collections and indexes.

Collections:
- councils     one doc per London borough: boundary polygon + repair rules (taxonomic memory)
- categories   one config doc per problem type (flexible schema per category)
- issues       one doc per real-world problem; many reports roll up into it
- reports      every photo submission, linked to its issue
- agent_memory Hermes agent state / short-term / long-term memory

If MONGODB_URI is not set, `get_db()` returns None and the pipeline runs in
offline mode (classification + local routing only) so the UI can still be built.
"""

from functools import lru_cache

from pymongo import ASCENDING, GEOSPHERE, MongoClient
from pymongo.database import Database

from app import config
from app.log import log


@lru_cache
def get_db() -> Database | None:
    """Return the Street Fixer database, or None when running offline."""
    if not config.MONGODB_URI:
        log.warning("MONGODB_URI not set: running in offline mode")
        return None
    client = MongoClient(config.MONGODB_URI, appname="street-fixer", serverSelectionTimeoutMS=8000)
    return client[config.DB_NAME]


def ensure_indexes(db: Database) -> None:
    """Create the standard (non-Atlas-Search) indexes. Safe to run repeatedly."""
    db.councils.create_index([("boundary", GEOSPHERE)])
    db.issues.create_index([("location", GEOSPHERE)])
    db.issues.create_index([("category", ASCENDING), ("status", ASCENDING)])
    db.issues.create_index([("ref", ASCENDING)], unique=True)
    db.reports.create_index([("issue_id", ASCENDING)])
    db.agent_memory.create_index([("kind", ASCENDING), ("issue_id", ASCENDING)])
    log.info("indexes ensured")
