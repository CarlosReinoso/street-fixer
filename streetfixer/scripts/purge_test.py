"""Delete every test report and test issue (test=True) and their photos.

Run: .venv/bin/python -m scripts.purge_test
"""

from app.db import get_db
from app.pipeline import UPLOAD_DIR


def main() -> None:
    db = get_db()
    if db is None:
        raise SystemExit("Set MONGODB_URI in .env first")
    photos = [r["photo"] for r in db.reports.find({"test": True}, {"photo": 1})]
    reports = db.reports.delete_many({"test": True}).deleted_count
    issues = db.issues.delete_many({"test": True}).deleted_count
    for name in photos:
        (UPLOAD_DIR / name).unlink(missing_ok=True)
    print(f"deleted {issues} test issues, {reports} test reports, {len(photos)} photos")


if __name__ == "__main__":
    main()
