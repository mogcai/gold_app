"""Standalone scraper — run by GitHub Actions every 30 minutes.

Fetches a fresh spot + CTF snapshot and appends it to `gold.db`. Exits with a
non-zero status on failure so the workflow shows up red in GitHub.
"""

from __future__ import annotations

import sys

import data_retriever as dr
import db


def main() -> int:
    spot = dr.get_gold_spot_snapshot()
    ctf = dr.get_chow_tai_fook_snapshot(spot_hkd_tael=spot["hkd_per_tael"])
    snapshot = {"fetched_at": __import__("time").time(), "spot": spot, "ctf": ctf}

    inserted = db.insert_snapshot(snapshot)
    if inserted:
        print(f"Inserted snapshot @ {snapshot['fetched_at']:.0f}")
    else:
        print("Snapshot already present — nothing to do.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Scrape failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
