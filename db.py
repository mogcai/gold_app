"""SQLite storage layer for gold price snapshots.

The database file (`gold.db`) is committed to the repo and updated by the
GitHub Actions scraper every 30 minutes. The Streamlit app reads it directly
and falls back to a live fetch when the DB is stale or missing.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

DB_FILE = Path(__file__).with_name("gold.db")

COLUMNS = [
    "timestamp_epoch", "timestamp", "spot_usd_oz", "usd_hkd",
    "spot_hkd_gram", "spot_hkd_tael", "ctf_9999_buy", "ctf_9999_sell",
    "ctf_pellet_buy", "ctf_pellet_sell", "premium_9999_sell", "premium_pellet_sell",
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    timestamp_epoch     REAL PRIMARY KEY,
    timestamp           TEXT NOT NULL,
    spot_usd_oz         REAL,
    usd_hkd             REAL,
    spot_hkd_gram       REAL,
    spot_hkd_tael       REAL,
    ctf_9999_buy        REAL,
    ctf_9999_sell       REAL,
    ctf_pellet_buy      REAL,
    ctf_pellet_sell     REAL,
    premium_9999_sell   REAL,
    premium_pellet_sell REAL
);
"""


def connect(db_path: Path | str = DB_FILE) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(_SCHEMA)
    return conn


def snapshot_to_row(snapshot: dict) -> dict:
    """Flatten a `load_snapshot()` dict into a DB row."""
    spot, ctf = snapshot["spot"], snapshot["ctf"]
    return {
        "timestamp_epoch": float(snapshot["fetched_at"]),
        "timestamp": datetime.fromtimestamp(snapshot["fetched_at"]).strftime("%Y-%m-%d %H:%M:%S"),
        "spot_usd_oz": spot["usd_per_oz"],
        "usd_hkd": spot["usd_hkd"],
        "spot_hkd_gram": spot["hkd_per_gram"],
        "spot_hkd_tael": spot["hkd_per_tael"],
        "ctf_9999_buy": ctf["gold_9999_buy"],
        "ctf_9999_sell": ctf["gold_9999_sell"],
        "ctf_pellet_buy": ctf["gold_pellet_buy"],
        "ctf_pellet_sell": ctf["gold_pellet_sell"],
        "premium_9999_sell": ctf.get("gold_9999_sell_premium"),
        "premium_pellet_sell": ctf.get("gold_pellet_sell_premium"),
    }


def insert_snapshot(snapshot: dict, db_path: Path | str = DB_FILE) -> bool:
    """Insert a snapshot row. Returns False if the timestamp already exists."""
    row = snapshot_to_row(snapshot)
    with connect(db_path) as conn:
        cur = conn.execute(
            f"INSERT OR IGNORE INTO snapshots ({', '.join(COLUMNS)}) "
            f"VALUES ({', '.join('?' * len(COLUMNS))})",
            [row[c] for c in COLUMNS],
        )
        return cur.rowcount > 0


def read_history(db_path: Path | str = DB_FILE) -> pd.DataFrame:
    """Return all snapshots as a DataFrame (empty if the DB/file is missing)."""
    if not Path(db_path).exists():
        return pd.DataFrame(columns=COLUMNS)
    try:
        with connect(db_path) as conn:
            return pd.read_sql_query(
                "SELECT * FROM snapshots ORDER BY timestamp_epoch", conn
            )
    except Exception:
        return pd.DataFrame(columns=COLUMNS)


def latest_epoch(db_path: Path | str = DB_FILE) -> float | None:
    """Epoch of the newest row, or None when the DB is empty/missing."""
    if not Path(db_path).exists():
        return None
    try:
        with connect(db_path) as conn:
            row = conn.execute("SELECT MAX(timestamp_epoch) FROM snapshots").fetchone()
        return float(row[0]) if row and row[0] is not None else None
    except Exception:
        return None
