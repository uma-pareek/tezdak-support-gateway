"""Ticket store with notes, status changes, reopen and an audit trail.

Changelog:
  v1  create/get/list/add_note/set_status
  v2  reopen() with reason; reopen_count column
  v3  audit rows for every mutation (ticket_audit)
"""

from __future__ import annotations

STATUSES = ("open", "pending", "resolved", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")
REOPENABLE = ("resolved", "closed")
KINDS_V1 = ("ndr", "wismo", "refund", "address", "other")  # TODO: kinds are free text now, drop this


class TicketError(ValueError):
    pass


class TicketStore:
    def __init__(self, db, events=None):
        self.db = db
        self.events = events

    # -- internals ---------------------------------------------------------
    def _audit(self, ticket_id: int, action: str, old=None, new=None, detail: str | None = None) -> None:
        self.db.execute(
            "INSERT INTO ticket_audit(ticket_id, action, old_value, new_value, detail, ts) VALUES (?,?,?,?,?,?)",
            (ticket_id, action, old, new, detail, self.db.now_iso()),
        )
        if self.events is not None:
            self.events.publish("ticket." + action, {"ticket_id": ticket_id, "old": old, "new": new})

    def _require(self, ticket_id: int) -> dict:
        row = self.db.query_one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if row is None:
            raise TicketError(f"ticket {ticket_id} not found")
        return row

    def _touch(self, ticket_id: int) -> None:
        self.db.execute("UPDATE tickets SET updated_at = ? WHERE id = ?", (self.db.now_iso(), ticket_id))

    # -- public api --------------------------------------------------------
    def create(self, awb: str, kind: str, summary: str, priority: str = "normal", source: str = "chat") -> int:
        if not awb or not kind:
            raise TicketError("awb and kind are required")
        if priority not in PRIORITIES:
            raise TicketError(f"bad priority {priority!r}")
        ts = self.db.now_iso()
        cur = self.db.execute(
            "INSERT INTO tickets(awb, kind, summary, priority, source, status, created_at, updated_at) "
            "VALUES (?,?,?,?,?,'open',?,?)",
            (awb, kind, summary, priority, source, ts, ts),
        )
        ticket_id = cur.lastrowid
        self._audit(ticket_id, "created", None, "open", f"{kind}/{priority}/{source}")
        return ticket_id

    def get(self, ticket_id: int) -> dict | None:
        row = self.db.query_one("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        if row is None:
            return None
        row["notes"] = self.db.query(
            "SELECT author, text, created_at FROM ticket_notes WHERE ticket_id = ? ORDER BY id", (ticket_id,)
        )
        return row

    def list(self, status: str | None = None, awb: str | None = None) -> list[dict]:
        sql, params, clauses = "SELECT * FROM tickets", [], []
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        if awb is not None:
            clauses.append("awb = ?")
            params.append(awb)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        return self.db.query(sql + " ORDER BY id", params)

    def add_note(self, ticket_id: int, text: str, author: str) -> int:
        self._require(ticket_id)
        if not text.strip():
            raise TicketError("empty note")
        cur = self.db.execute(
            "INSERT INTO ticket_notes(ticket_id, author, text, created_at) VALUES (?,?,?,?)",
            (ticket_id, author, text, self.db.now_iso()),
        )
        self._touch(ticket_id)
        self._audit(ticket_id, "note_added", None, None, author)
        return cur.lastrowid

    def set_status(self, ticket_id: int, status: str) -> None:
        if status not in STATUSES:
            raise TicketError(f"bad status {status!r}")
        row = self._require(ticket_id)
        if row["status"] == status:
            return
        self.db.execute(
            "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, self.db.now_iso(), ticket_id)
        )
        self._audit(ticket_id, "status_changed", row["status"], status)

    def reopen(self, ticket_id: int, reason: str) -> None:
        row = self._require(ticket_id)
        if row["status"] not in REOPENABLE:
            raise TicketError(f"ticket {ticket_id} is {row['status']}, only resolved or closed can reopen")
        if not reason.strip():
            raise TicketError("reopen needs a reason")
        self.db.execute(
            "UPDATE tickets SET status = 'open', reopen_count = reopen_count + 1, updated_at = ? WHERE id = ?",
            (self.db.now_iso(), ticket_id),
        )
        self._audit(ticket_id, "reopened", row["status"], "open", reason)
        self.add_note(ticket_id, f"Reopened: {reason}", "system")

    def audit_trail(self, ticket_id: int) -> list[dict]:
        self._require(ticket_id)
        return self.db.query("SELECT * FROM ticket_audit WHERE ticket_id = ? ORDER BY id", (ticket_id,))

    def reopen_count(self, ticket_id: int) -> int:
        return self._require(ticket_id)["reopen_count"]

    def open_for_awb(self, awb: str) -> list[dict]:
        return [t for t in self.list(awb=awb) if t["status"] in ("open", "pending")]

    def count_by_status(self) -> dict:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM tickets GROUP BY status")
        return {r["status"]: r["n"] for r in rows}

    # deprecated shim
    def close_ticket(self, ticket_id: int) -> None:
        self.set_status(ticket_id, "closed")

    # -- reporting helpers (v3) -------------------------------------------
    def overdue(self, now, sla_hours: int = 48) -> list[dict]:
        """Open or pending tickets whose last update is older than the SLA."""
        from datetime import timedelta
        from .db import from_iso
        cutoff = now - timedelta(hours=sla_hours)
        return [t for t in self.list() if t["status"] in ("open", "pending") and from_iso(t["updated_at"]) < cutoff]

    def by_kind(self) -> dict:
        rows = self.db.query("SELECT kind, COUNT(*) AS n FROM tickets GROUP BY kind ORDER BY kind")
        return {r["kind"]: r["n"] for r in rows}

    def reopened(self) -> list[dict]:
        return self.db.query("SELECT * FROM tickets WHERE reopen_count > 0 ORDER BY id")

    def export_rows(self) -> list[dict]:
        """Flat rows for CSV export: ticket fields plus note count."""
        rows = self.db.query(
            "SELECT t.*, (SELECT COUNT(*) FROM ticket_notes n WHERE n.ticket_id = t.id) AS note_count "
            "FROM tickets t ORDER BY t.id"
        )
        return rows

    def merge(self, keep_id: int, drop_id: int) -> None:
        """Fold a duplicate ticket into another: notes move over, the duplicate is closed."""
        self._require(keep_id)
        self._require(drop_id)
        if keep_id == drop_id:
            raise TicketError("cannot merge a ticket into itself")
        self.db.execute("UPDATE ticket_notes SET ticket_id = ? WHERE ticket_id = ?", (keep_id, drop_id))
        self._audit(keep_id, "merged", str(drop_id), str(keep_id))
        self.set_status(drop_id, "closed")
