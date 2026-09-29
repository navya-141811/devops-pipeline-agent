"""
database.py — SQLite schema + helpers for deployment history and service stats.

Tables:
    deployments  — every recorded deployment with outcome
    service_stats — aggregated failure rate per service (updated on each outcome)
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "deployments.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist."""
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS deployments (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                deployment_id TEXT    UNIQUE NOT NULL,
                service       TEXT    NOT NULL,
                environment   TEXT    NOT NULL,
                version       TEXT    NOT NULL,
                deployed_by   TEXT    NOT NULL,
                outcome       TEXT,                        -- NULL until recorded
                deployed_at   TEXT    NOT NULL,
                recorded_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS service_stats (
                service        TEXT PRIMARY KEY,
                total          INTEGER NOT NULL DEFAULT 0,
                failures       INTEGER NOT NULL DEFAULT 0,
                last_updated   TEXT    NOT NULL
            );
        """)


# ── Deployments ────────────────────────────────────────────────────────────────

def insert_deployment(deployment_id: str, service: str, environment: str,
                      version: str, deployed_by: str, deployed_at: str = None) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO deployments
               (deployment_id, service, environment, version, deployed_by, deployed_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (deployment_id, service, environment, version, deployed_by,
             deployed_at or datetime.utcnow().isoformat()),
        )


def record_outcome(deployment_id: str, service: str, outcome: str) -> None:
    """Update deployment outcome and refresh service_stats."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE deployments SET outcome=?, recorded_at=? WHERE deployment_id=?",
            (outcome, datetime.utcnow().isoformat(), deployment_id),
        )
        # Upsert service_stats
        conn.execute(
            """INSERT INTO service_stats (service, total, failures, last_updated)
               VALUES (?, 1, ?, ?)
               ON CONFLICT(service) DO UPDATE SET
                   total        = total + 1,
                   failures     = failures + excluded.failures,
                   last_updated = excluded.last_updated""",
            (service, 1 if outcome in ("failed", "rolled_back") else 0,
             datetime.utcnow().isoformat()),
        )


def get_service_failure_rate(service: str) -> float:
    """Returns failure rate 0.0–1.0 for a service. 0.0 if no history."""
    with get_conn() as conn:
        row = conn.execute(
            "SELECT total, failures FROM service_stats WHERE service=?", (service,)
        ).fetchone()
    if not row or row["total"] == 0:
        return 0.0
    return round(row["failures"] / row["total"], 3)


def list_deployments(service: str | None = None, limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        if service:
            rows = conn.execute(
                "SELECT * FROM deployments WHERE service=? ORDER BY deployed_at DESC LIMIT ?",
                (service, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM deployments ORDER BY deployed_at DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# Auto-init on import
init_db()
