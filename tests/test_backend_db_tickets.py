import unittest
from datetime import datetime

from tezdak.backend.db import IST, MIGRATIONS, Db
from tezdak.backend.events import EventBus
from tezdak.backend.tickets import TicketError, TicketStore


class DbTests(unittest.TestCase):
    def test_migrations_apply_in_order(self):
        db = Db()
        self.assertEqual(db.schema_version(), MIGRATIONS[-1][0])
        for name in ("tickets", "customers", "orders", "audit_log", "address_history"):
            self.assertIn(name, db.table_names())

    def test_migrate_is_idempotent(self):
        db = Db()
        self.assertEqual(db.migrate(), db.migrate())

    def test_partial_target_then_full(self):
        db = Db(migrate=False)
        self.assertEqual(db.migrate(target=2), 2)
        self.assertNotIn("orders", db.table_names())
        db.migrate()
        self.assertIn("orders", db.table_names())

    def test_legacy_shim(self):
        self.assertEqual(Db().run_migrations(), MIGRATIONS[-1][0])


class TicketTests(unittest.TestCase):
    def setUp(self):
        self.db = Db()
        self.bus = EventBus()
        self.seen = []
        self.bus.subscribe("ticket.*", lambda t, p: self.seen.append(t))
        self.store = TicketStore(self.db, self.bus)

    def test_create_get_list(self):
        tid = self.store.create("TZ1", "ndr", "rider did not come", priority="high")
        t = self.store.get(tid)
        self.assertEqual((t["awb"], t["status"], t["priority"], t["source"]), ("TZ1", "open", "high", "chat"))
        self.assertEqual(len(self.store.list(awb="TZ1")), 1)
        self.assertEqual(self.store.list(status="closed"), [])
        self.assertIsNone(self.store.get(999))

    def test_notes_and_validation(self):
        tid = self.store.create("TZ1", "ndr", "s")
        self.store.add_note(tid, "called customer", "agent")
        self.assertEqual(self.store.get(tid)["notes"][0]["author"], "agent")
        with self.assertRaises(TicketError):
            self.store.add_note(tid, "  ", "agent")
        with self.assertRaises(TicketError):
            self.store.add_note(404, "x", "agent")
        with self.assertRaises(TicketError):
            self.store.create("TZ1", "ndr", "s", priority="whenever")
        with self.assertRaises(TicketError):
            self.store.set_status(tid, "weird")

    def test_reopen_flow_and_audit(self):
        tid = self.store.create("TZ1", "ndr", "s")
        with self.assertRaises(TicketError):
            self.store.reopen(tid, "still open")
        self.store.set_status(tid, "resolved")
        self.store.reopen(tid, "customer wrote again on day 2")
        t = self.store.get(tid)
        self.assertEqual(t["status"], "open")
        self.assertEqual(t["reopen_count"], 1)
        self.assertIn("Reopened", t["notes"][-1]["text"])
        actions = [a["action"] for a in self.store.audit_trail(tid)]
        self.assertEqual(actions, ["created", "status_changed", "reopened", "note_added"])
        self.store.set_status(tid, "closed")
        self.store.reopen(tid, "again")
        self.assertEqual(self.store.reopen_count(tid), 2)
        self.assertIn("ticket.reopened", self.seen)

    def test_reopen_needs_reason(self):
        tid = self.store.create("TZ1", "ndr", "s")
        self.store.set_status(tid, "closed")
        with self.assertRaises(TicketError):
            self.store.reopen(tid, " ")

    def test_helpers(self):
        a = self.store.create("TZ1", "ndr", "s")
        b = self.store.create("TZ1", "wismo", "s")
        self.store.set_status(a, "closed")
        self.assertEqual(len(self.store.open_for_awb("TZ1")), 1)
        self.assertEqual(self.store.count_by_status(), {"closed": 1, "open": 1})
        self.store.close_ticket(b)
        self.assertEqual(self.store.open_for_awb("TZ1"), [])

    def test_timestamps_follow_clock(self):
        fixed = datetime(2026, 11, 2, 12, 10, tzinfo=IST)
        store = TicketStore(Db(clock=lambda: fixed))
        tid = store.create("TZ1", "ndr", "s")
        self.assertTrue(store.get(tid)["created_at"].startswith("2026-11-02T12:10"))

    def test_reporting_helpers(self):
        from datetime import timedelta
        a = self.store.create("TZ1", "ndr", "s")
        b = self.store.create("TZ2", "wismo", "s")
        self.store.add_note(b, "n", "agent")
        later = self.db.now() + timedelta(hours=72)
        self.assertEqual(len(self.store.overdue(later)), 2)
        self.assertEqual(self.store.overdue(self.db.now()), [])
        self.assertEqual(self.store.by_kind(), {"ndr": 1, "wismo": 1})
        self.store.set_status(a, "resolved")
        self.store.reopen(a, "again")
        self.assertEqual([t["id"] for t in self.store.reopened()], [a])
        self.assertEqual({r["id"]: r["note_count"] for r in self.store.export_rows()}, {a: 1, b: 1})

    def test_merge(self):
        a = self.store.create("TZ1", "ndr", "s")
        b = self.store.create("TZ1", "ndr", "dup")
        self.store.add_note(b, "from dup", "agent")
        self.store.merge(a, b)
        self.assertEqual(self.store.get(a)["notes"][0]["text"], "from dup")
        self.assertEqual(self.store.get(b)["status"], "closed")
        with self.assertRaises(TicketError):
            self.store.merge(a, a)


if __name__ == "__main__":
    unittest.main()
