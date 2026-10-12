import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from tezdak.backend.customers import CustomerStore, normalize_phone
from tezdak.backend.db import IST, Db
from tezdak.backend.events import AuditLog, EventBus
from tezdak.backend.flags import STALE_FLAGS, FlagService
from tezdak.backend.orders import OrderError, OrderStore
from tezdak.backend.settings import Settings, SettingsError


class CustomerTests(unittest.TestCase):
    def setUp(self):
        self.store = CustomerStore(Db())
        self.now = datetime(2026, 11, 2, 12, 0, tzinfo=IST)

    def test_phone_normalisation(self):
        self.assertEqual(normalize_phone("+91-90000-00001"), normalize_phone("9000000001"))
        self.assertEqual(normalize_phone(""), "")

    def test_upsert_and_get(self):
        self.store.upsert("+91-90000-00001", "Asha", "hinglish")
        self.store.upsert("+919000000001", None, "english")
        c = self.store.get_by_phone("+91-90000-00001")
        self.assertEqual((c["name"], c["language"]), ("Asha", "english"))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(self.store.upsert("+91-90000-00002", "B", "klingon")["language"], "english")
        with self.assertRaises(ValueError):
            self.store.upsert("", "x")

    def test_goodwill_window(self):
        p = "+91-90000-00001"
        self.store.record_goodwill(p, 50, self.now - timedelta(days=40))
        self.store.record_goodwill(p, 50, self.now - timedelta(days=10))
        self.store.record_goodwill(p, 100, self.now - timedelta(days=1))
        hist = self.store.goodwill_history(p, 30, self.now)
        self.assertEqual([h["amount_inr"] for h in hist], [50, 100])
        self.assertEqual(self.store.goodwill_total(p, 30, self.now), 150)
        self.assertTrue(self.store.is_repeat_claimant(p, self.now))
        self.assertFalse(self.store.is_repeat_claimant("+91-90000-00009", self.now))
        with self.assertRaises(ValueError):
            self.store.record_goodwill(p, 0, self.now)

    def test_search_and_top_goodwill(self):
        self.store.upsert("+91-90000-00001", "Asha")
        self.store.upsert("+91-90000-00002", "Bala")
        self.assertEqual([c["name"] for c in self.store.search("Bal")], ["Bala"])
        self.store.record_goodwill("+91-90000-00001", 50, self.now)
        self.store.record_goodwill("+91-90000-00001", 50, self.now)
        self.store.record_goodwill("+91-90000-00002", 70, self.now)
        top = self.store.top_goodwill(30, self.now)
        self.assertEqual((top[0]["phone"], top[0]["total_inr"]), ("+919000000001", 100))


class OrderTests(unittest.TestCase):
    def setUp(self):
        self.bus = EventBus()
        self.orders = OrderStore(Db(), self.bus)
        self.orders.put("TZ1", "DesiMart", "apparel", [{"name": "kurta", "qty": 1}], 999, "old addr", "+919000000001")

    def test_put_get(self):
        o = self.orders.get("TZ1")
        self.assertEqual((o["seller"], o["value_inr"], o["cancelled"]), ("DesiMart", 999, False))
        self.assertEqual(o["items"][0]["name"], "kurta")
        self.assertIsNone(self.orders.get("nope"))

    def test_address_history(self):
        self.orders.update_address("TZ1", "new addr", "customer")
        self.orders.update_address("TZ1", "newer addr", "agent")
        h = self.orders.address_history("TZ1")
        self.assertEqual([(x["old_text"], x["new_text"]) for x in h], [("old addr", "new addr"), ("new addr", "newer addr")])
        self.assertEqual(self.orders.get("TZ1")["address_text"], "newer addr")

    def test_cancel_blocks_updates(self):
        self.orders.cancel("TZ1", "customer")
        self.assertTrue(self.orders.get("TZ1")["cancelled"])
        with self.assertRaises(OrderError):
            self.orders.update_address("TZ1", "x", "customer")
        self.assertTrue(self.orders.cancel("TZ1", "again")["cancelled"])
        with self.assertRaises(OrderError):
            self.orders.cancel("missing", "x")

    def test_put_keeps_cancel_state_and_lookups(self):
        self.orders.cancel("TZ1", "customer")
        self.orders.put("TZ1", "DesiMart", "apparel", [], 999, "addr", "+919000000001")
        self.assertTrue(self.orders.get("TZ1")["cancelled"])
        self.assertEqual(len(self.orders.by_phone("+919000000001")), 1)
        self.assertEqual(len(self.orders.by_seller("DesiMart")), 1)

    def test_empty_address_rejected(self):
        with self.assertRaises(OrderError):
            self.orders.update_address("TZ1", "  ", "customer")


class EventTests(unittest.TestCase):
    def test_bus_prefix_and_errors(self):
        bus, got = EventBus(), []
        bus.subscribe("a.*", lambda t, p: got.append(t))
        bus.subscribe("a.boom", lambda t, p: 1 / 0)
        self.assertEqual(bus.publish("a.boom", {}), 1)
        self.assertEqual(bus.publish("b.x"), 0)
        self.assertEqual(got, ["a.boom"])
        self.assertEqual(len(bus.errors), 1)

    def test_audit_log_append_only(self):
        db = Db()
        log, bus = AuditLog(db), EventBus()
        log.attach(bus)
        bus.publish("order.cancelled", {"awb": "TZ1"})
        bus.publish("ticket.created", {"ticket_id": 1})
        self.assertEqual(log.count(), 2)
        self.assertEqual(log.entries("order.")[0]["payload"], {"awb": "TZ1"})
        self.assertFalse(hasattr(log, "delete"))
        self.assertEqual(len(log.entries(limit=1)), 1)


class FlagSettingsTests(unittest.TestCase):
    def test_flags_env_overrides(self):
        f = FlagService(environ={"TEZDAK_FLAG_DELAY_NOTIFIER": "true", "TEZDAK_FLAG_HANDOFF": "off"})
        self.assertTrue(f.is_enabled("delay_notifier"))
        self.assertFalse(f.is_enabled("handoff"))
        self.assertTrue(f.is_enabled("cancel_order"))
        self.assertFalse(f.is_enabled("unknown_flag"))
        self.assertTrue(f.is_enabled("unknown_flag", default=True))

    def test_flags_garbage_env_uses_default(self):
        f = FlagService(environ={"TEZDAK_FLAG_HANDOFF": "maybe"})
        self.assertTrue(f.is_enabled("handoff"))

    def test_stale_flags_listed_not_active(self):
        f = FlagService(environ={})
        self.assertEqual(set(f.stale()), set(STALE_FLAGS))
        self.assertFalse(set(f.active()) & set(STALE_FLAGS))
        f.set("voice_notes", True)
        self.assertIn("voice_notes", f.active())

    def test_flags_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "flags.json")
            with open(path, "w") as fh:
                json.dump({"slot_picker": False}, fh)
            self.assertFalse(FlagService(path=path, environ={}).is_enabled("slot_picker"))
            self.assertTrue(FlagService(path=os.path.join(d, "none.json"), environ={}).is_enabled("slot_picker"))

    def test_settings_layers(self):
        s = Settings(file_values={"max_attempts": 4, "ticket_sla_hours": 24},
                     environ={"TEZDAK_SETTING_TICKET_SLA_HOURS": "12"})
        self.assertEqual(s.get("hub_cutoff_hour"), 11)
        self.assertEqual(s.source_of("hub_cutoff_hour"), "default")
        self.assertEqual((s.get("max_attempts"), s.source_of("max_attempts")), (4, "file"))
        self.assertEqual((s.get("ticket_sla_hours"), s.source_of("ticket_sla_hours")), (12, "env"))
        s.set("max_attempts", 5)
        self.assertEqual(s.source_of("max_attempts"), "override")
        self.assertIsNone(s.get("nope"))
        with self.assertRaises(SettingsError):
            s.source_of("nope")

    def test_settings_stale_keys(self):
        s = Settings(environ={})
        self.assertIn("refund_sla_days", s.stale_keys())
        self.assertIn("refund_sla_days", s.as_dict())


if __name__ == "__main__":
    unittest.main()
