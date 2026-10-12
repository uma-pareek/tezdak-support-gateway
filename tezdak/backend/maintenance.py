"""Housekeeping: integrity check, backup, retention of old closed tickets."""

import sqlite3
from datetime import timedelta

from .db import Db, from_iso


def integrity_ok(db: Db) -> bool:
    return db.query_one("PRAGMA integrity_check")["integrity_check"] == "ok"


def backup_to(db: Db, path: str) -> int:
    """Copy the live database into a file with the sqlite backup API; returns the schema version copied."""
    dest = sqlite3.connect(path)
    try:
        db.conn.backup(dest)
        row = dest.execute("SELECT MAX(version) FROM schema_version").fetchone()
        return row[0] or 0
    finally:
        dest.close()


def purge_closed_tickets(backend, older_than_days: int = 180) -> int:
    """Delete closed tickets (and their notes and audit rows) not touched for N days. Returns count."""
    cutoff = backend.db.now() - timedelta(days=older_than_days)
    victims = [t["id"] for t in backend.tickets.list(status="closed") if from_iso(t["updated_at"]) < cutoff]
    for tid in victims:
        for table in ("ticket_notes", "ticket_audit"):
            backend.db.execute(f"DELETE FROM {table} WHERE ticket_id = ?", (tid,))
        backend.db.execute("DELETE FROM tickets WHERE id = ?", (tid,))
    if victims:
        backend.audit.append("maintenance.purged_tickets", {"count": len(victims)})
    return len(victims)


def table_counts(db: Db) -> dict:
    out = {}
    for name in db.table_names():
        if name.startswith("sqlite_"):
            continue
        out[name] = db.query_one(f'SELECT COUNT(*) AS n FROM "{name}"')["n"]
    return out
