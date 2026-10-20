import csv
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from tezdak.backend import exporters, maintenance, sla
from tezdak.backend.db import IST, Db
from tezdak.backend.facade import Backend


def at(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


class SlaTests(unittest.TestCase):
    def test_parse_hours(self):
        self.assertEqual(sla.parse_hours("09:00-21:00"), (540, 1260))
        for bad in ("9-21", "21:00-09:00", "x"):
            with self.assertRaises(ValueError):
                sla.parse_hours(bad)

    def test_business_minutes_skip_night(self):
        win = (540, 1260)
        self.assertEqual(sla.business_minutes_between(at(2, 20), at(3, 10), win), 60 + 60)
        self.assertEqual(sla.business_minutes_between(at(2, 22), at(3, 8), win), 0)
        self.assertEqual(sla.business_minutes_between(at(3, 10), at(2, 10), win), 0)

    def test_breach_uses_priority_and_status(self):
        now = {"v": at(2, 10)}
        b = Backend.in_memory(clock=lambda: now["v"], settings={"ticket_sla_hours": 4})
        urgent = b.tickets.create("TZ1", "ndr", "s", priority="urgent")
        normal = b.tickets.create("TZ2", "ndr", "s")
        done = b.tickets.create("TZ3", "ndr", "s")
        b.tickets.set_status(done, "closed")
        now["v"] = at(2, 12)
        self.assertEqual([t["id"] for t in sla.breached_tickets(b.tickets, now["v"], b.settings)], [urgent])
        now["v"] = at(2, 16)
        ids = [t["id"] for t in sla.breached_tickets(b.tickets, now["v"], b.settings)]
        self.assertEqual(ids, [urgent, normal])

    def test_wall_clock_mode_counts_night(self):
        b = Backend.in_memory(clock=lambda: at(2, 20), settings={"ticket_sla_hours": 8})
        b.tickets.create("TZ1", "ndr", "s")
        morning = at(3, 8)
        self.assertEqual(sla.breached_tickets(b.tickets, morning, b.settings, business=True), [])
        self.assertEqual(len(sla.breached_tickets(b.tickets, morning, b.settings, business=False)), 1)


class ExportMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.b = Backend.in_memory(clock=lambda: at(2, 12))
        self.b.orders.put("TZ1", "DesiMart", "apparel", [], 500, "addr", "+919000000001")
        self.b.tickets.create("TZ1", "ndr", "s")

    def test_csv_exports(self):
        rows = list(csv.DictReader(io.StringIO(exporters.tickets_csv(self.b))))
        self.assertEqual((rows[0]["awb"], rows[0]["note_count"]), ("TZ1", "0"))
        orows = list(csv.DictReader(io.StringIO(exporters.orders_csv(self.b))))
        self.assertEqual(orows[0]["value_inr"], "500")

    def test_json_dump_parses(self):
        data = json.loads(exporters.dump_json(self.b))
        self.assertEqual(len(data["tickets"]), 1)
        self.assertTrue(data["audit"])

    def test_redact_phone(self):
        self.assertEqual(exporters.redact_phone("+919000000001"), "+9190XXXX0001")
        self.assertTrue(exporters.redact_phone("+919000000001").endswith("0001"))
        self.assertEqual(exporters.redact_phone("123"), "XXXX")

    def test_backup_and_integrity(self):
        self.assertTrue(maintenance.integrity_ok(self.b.db))
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bk.db")
            self.assertEqual(maintenance.backup_to(self.b.db, path), self.b.db.schema_version())
            copy = Db(path, migrate=False)
            self.assertEqual(maintenance.table_counts(copy)["tickets"], 1)
            copy.close()

    def test_purge_old_closed_tickets(self):
        now = {"v": at(2, 12)}
        b = Backend.in_memory(clock=lambda: now["v"])
        old = b.tickets.create("TZ1", "ndr", "s")
        b.tickets.add_note(old, "n", "agent")
        b.tickets.set_status(old, "closed")
        now["v"] = at(2, 12) + timedelta(days=150)
        fresh = b.tickets.create("TZ2", "ndr", "s")
        b.tickets.set_status(fresh, "closed")
        now["v"] = at(2, 12) + timedelta(days=200)
        self.assertEqual(maintenance.purge_closed_tickets(b, older_than_days=180), 1)
        self.assertEqual([t["id"] for t in b.tickets.list()], [fresh])
        self.assertTrue(b.audit.entries("maintenance."))


if __name__ == "__main__":
    unittest.main()
