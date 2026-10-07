"""In-process event bus and an append-only audit log stored in the database."""

import json
from collections import defaultdict


class EventBus:
    """Synchronous pub/sub. Handlers that raise are recorded, never propagated."""

    def __init__(self):
        self._subs = defaultdict(list)
        self.errors: list[tuple[str, str]] = []
        self.published = 0

    def subscribe(self, topic: str, handler) -> None:
        """topic may end with '*' to match a prefix, e.g. 'ticket.*'."""
        self._subs[topic].append(handler)

    def unsubscribe(self, topic: str, handler) -> None:
        if handler in self._subs.get(topic, []):
            self._subs[topic].remove(handler)

    def publish(self, topic: str, payload: dict | None = None) -> int:
        self.published += 1
        delivered = 0
        for pattern, handlers in list(self._subs.items()):
            if not self._matches(pattern, topic):
                continue
            for handler in list(handlers):
                try:
                    handler(topic, payload or {})
                    delivered += 1
                except Exception as exc:  # noqa: BLE001 - a bad subscriber must not break the caller
                    self.errors.append((topic, repr(exc)))
        return delivered

    @staticmethod
    def _matches(pattern: str, topic: str) -> bool:
        if pattern.endswith("*"):
            return topic.startswith(pattern[:-1])
        return pattern == topic


class AuditLog:
    """Append-only: there is intentionally no update or delete."""

    def __init__(self, db):
        self.db = db

    def append(self, topic: str, payload: dict | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO audit_log(topic, payload_json, ts) VALUES (?,?,?)",
            (topic, json.dumps(payload or {}, sort_keys=True), self.db.now_iso()),
        )
        return cur.lastrowid

    def entries(self, topic_prefix: str | None = None, limit: int | None = None) -> list[dict]:
        sql, params = "SELECT seq, topic, payload_json, ts FROM audit_log", []
        if topic_prefix:
            sql += " WHERE topic LIKE ?"
            params.append(topic_prefix + "%")
        sql += " ORDER BY seq"
        if limit:
            sql += " LIMIT ?"
            params.append(limit)
        out = self.db.query(sql, params)
        for row in out:
            row["payload"] = json.loads(row.pop("payload_json"))
        return out

    def count(self) -> int:
        return self.db.query_one("SELECT COUNT(*) AS n FROM audit_log")["n"]

    def attach(self, bus: EventBus, pattern: str = "*") -> None:
        """Mirror bus events into the log."""
        bus.subscribe(pattern, lambda topic, payload: self.append(topic, payload))
