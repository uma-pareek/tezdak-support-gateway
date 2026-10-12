"""Customer profiles keyed by phone, plus the goodwill ledger."""

from datetime import datetime, timedelta

from .db import from_iso, to_iso

LANGUAGES = ("english", "hinglish")


def normalize_phone(phone: str) -> str:
    """Keep digits and a leading plus; '+91-90000-00001' and '+919000000001' compare equal."""
    if phone is None:
        return ""
    kept = "".join(ch for ch in phone if ch.isdigit())
    if len(kept) == 10:
        kept = "91" + kept
    return "+" + kept if kept else ""


class CustomerStore:
    def __init__(self, db):
        self.db = db

    def upsert(self, phone: str, name: str | None = None, language: str = "english") -> dict:
        key = normalize_phone(phone)
        if not key:
            raise ValueError("phone required")
        if language not in LANGUAGES:
            language = "english"
        ts = self.db.now_iso()
        existing = self.get_by_phone(key)
        if existing is None:
            self.db.execute(
                "INSERT INTO customers(phone, name, language, created_at, updated_at) VALUES (?,?,?,?,?)",
                (key, name, language, ts, ts),
            )
        else:
            self.db.execute(
                "UPDATE customers SET name = ?, language = ?, updated_at = ? WHERE phone = ?",
                (name if name is not None else existing["name"], language, ts, key),
            )
        return self.get_by_phone(key)

    def get_by_phone(self, phone: str) -> dict | None:
        return self.db.query_one("SELECT * FROM customers WHERE phone = ?", (normalize_phone(phone),))

    def record_goodwill(self, phone: str, amount_inr: int, ts: datetime) -> int:
        if amount_inr <= 0:
            raise ValueError("goodwill amount must be positive")
        cur = self.db.execute(
            "INSERT INTO goodwill(phone, amount_inr, ts) VALUES (?,?,?)",
            (normalize_phone(phone), int(amount_inr), to_iso(ts)),
        )
        return cur.lastrowid

    def goodwill_history(self, phone: str, days: int, now: datetime) -> list[dict]:
        since = now - timedelta(days=days)
        rows = self.db.query(
            "SELECT amount_inr, ts FROM goodwill WHERE phone = ? ORDER BY ts", (normalize_phone(phone),)
        )
        return [r for r in rows if since <= from_iso(r["ts"]) <= now]

    def goodwill_total(self, phone: str, days: int, now: datetime) -> int:
        return sum(r["amount_inr"] for r in self.goodwill_history(phone, days, now))

    def is_repeat_claimant(self, phone: str, now: datetime, days: int = 30) -> bool:
        return bool(self.goodwill_history(phone, days, now))

    def count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) AS n FROM customers")["n"]

    def search(self, text: str, limit: int = 20) -> list[dict]:
        like = f"%{text}%"
        return self.db.query(
            "SELECT * FROM customers WHERE phone LIKE ? OR name LIKE ? ORDER BY phone LIMIT ?", (like, like, limit)
        )

    def top_goodwill(self, days: int, now: datetime, limit: int = 5) -> list[dict]:
        """Phones with the most goodwill rupees in the window (used by the ops export)."""
        since = to_iso(now - timedelta(days=days))
        return self.db.query(
            "SELECT phone, SUM(amount_inr) AS total_inr, COUNT(*) AS n FROM goodwill WHERE ts >= ? "
            "GROUP BY phone ORDER BY total_inr DESC, phone LIMIT ?", (since, limit)
        )
