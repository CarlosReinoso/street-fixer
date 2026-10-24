"""After the hackathon: back up the database, then terminate the Atlas cluster.

Run by the systemd user timer `streetfixer-close.timer` (Sun 25 Oct 2026, 20:00),
or by hand: .venv/bin/python -m scripts.close_cluster

Terminating uses the Atlas Admin API and needs an API key with Project Owner
on the project, in .env:
  ATLAS_PUBLIC_KEY=...    ATLAS_PRIVATE_KEY=...
Without them, or if the backup fails, nothing is terminated: a desktop
notification asks for the cluster to be terminated by hand instead.
Local photos in uploads/ are untouched (they never lived in Atlas).
"""

import os
import subprocess

import httpx

from app.log import log
from scripts.backup import backup

PROJECT_ID = "6adb7a9426a310f87da23eab"
CLUSTER = "streetfixer"
API = f"https://cloud.mongodb.com/api/atlas/v2/groups/{PROJECT_ID}/clusters/{CLUSTER}"
HEADERS = {"Accept": "application/vnd.atlas.2023-02-01+json"}


def notify(message: str) -> None:
    log.warning(message)
    subprocess.run(["notify-send", "-u", "critical", "Street Fixer Atlas", message], check=False)


def main() -> None:
    try:
        folder = backup()
    except BaseException as e:  # SystemExit from a failed check included
        notify(f"Backup failed, cluster NOT terminated: {e}")
        raise SystemExit(1)

    public, private = os.getenv("ATLAS_PUBLIC_KEY"), os.getenv("ATLAS_PRIVATE_KEY")
    if not (public and private):
        notify(f"Backup saved to {folder}. No Atlas API key in .env: terminate '{CLUSTER}' by hand in Atlas.")
        return

    resp = httpx.delete(API, headers=HEADERS, auth=httpx.DigestAuth(public, private), timeout=30)
    if resp.status_code in (202, 204):
        notify(f"Backup saved to {folder}. Cluster '{CLUSTER}' is terminating.")
    else:
        notify(f"Backup saved to {folder}. Terminate failed ({resp.status_code}): {resp.text[:200]}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
