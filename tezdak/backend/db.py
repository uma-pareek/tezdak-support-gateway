"""Thin sqlite3 wrapper with a numbered migration runner.

Changelog:
  v1  initial tickets / notes / audit tables
  v2  customers + goodwill ledger
  v3  orders + address history
  v4  event audit log
  v5  tickets.reopen_count (added with the reopen feature)
  v6  tickets.source index (cheap, helps the ops export)
"""

import sqlite3
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

MIGRATIONS = [
    (1, """
        CREATE TABLE tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            awb TEXT NOT NULL,
            kind TEXT NOT NULL,
            summary TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'normal',
            source TEXT NOT NULL DEFAULT 'chat',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE ticket_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            author TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE ticket_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL REFERENCES tickets(id),
            action TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            detail TEXT,
            ts TEXT NOT NULL
        );
        CREATE INDEX idx_tickets_awb ON tickets(awb);
    """),
    (2, """
        CREATE TABLE customers (
            phone TEXT PRIMARY KEY,
            name TEXT,
            language TEXT NOT NULL DEFAULT 'english',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE goodwill (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            amount_inr INTEGER NOT NULL,
            ts TEXT NOT NULL
        );
        CREATE INDEX idx_goodwill_phone ON goodwill(phone);
    """),
    (3, """
        CREATE TABLE orders (
            awb TEXT PRIMARY KEY,
            seller TEXT,
            category TEXT,
            items_json TEXT NOT NULL,
            value_inr INTEGER NOT NULL,
            address_text TEXT,
            phone TEXT,
            cancelled INTEGER NOT NULL DEFAULT 0,
            cancelled_by TEXT
        );
        CREATE TABLE address_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            awb TEXT NOT NULL,
            old_text TEXT,
            new_text TEXT,
            by TEXT NOT NULL,
            ts TEXT NOT NULL
        );
    """),
    (4, """
        CREATE TABLE audit_log (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            ts TEXT NOT NULL
        );
    """),
    (5, "ALTER TABLE tickets ADD COLUMN reopen_count INTEGER NOT NULL DEFAULT 0;"),
    (6, "CREATE INDEX idx_tickets_source ON tickets(source);"),
]


def ist_now() -> datetime:
    return datetime.now(IST)


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(IST).isoformat()


def from_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


class Db:
    """sqlite3 connection plus clock. `:memory:` unless a path is given."""

    def __init__(self, path: str = ":memory:", clock=None, migrate: bool = True):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.clock = clock or ist_now
        if migrate:
            self.migrate()

    # -- clock -------------------------------------------------------------
    def now(self) -> datetime:
        return self.clock()

    def now_iso(self) -> str:
        return to_iso(self.now())

    def set_clock(self, clock) -> None:
        self.clock = clock

    # -- migrations --------------------------------------------------------
    def schema_version(self) -> int:
        self.conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
        return row["v"] or 0

    def migrate(self, target: int | None = None) -> int:
        current = self.schema_version()
        for version, sql in MIGRATIONS:
            if version <= current:
                continue
            if target is not None and version > target:
                break
            try:
                self.conn.executescript("BEGIN;" + sql)
                self.conn.execute("INSERT INTO schema_version(version) VALUES (?)", (version,))
                self.conn.commit()
            except sqlite3.Error:
                self.conn.rollback()
                raise
        return self.schema_version()

    # -- query helpers -----------------------------------------------------
    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query(self, sql: str, params=()) -> list[dict]:
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params=()) -> dict | None:
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def table_names(self) -> list[str]:
        rows = self.query("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        return [r["name"] for r in rows]

    def close(self) -> None:
        self.conn.close()

    # deprecated shim: older callers used run_migrations()
    def run_migrations(self) -> int:
        return self.migrate()
