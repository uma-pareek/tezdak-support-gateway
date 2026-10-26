import json
import os
import tempfile
import threading
import time
import unittest

from tezdak.tools_ext import (Executor, SchemaError, ToolRegistry, TTLCache, build_handlers,
                              tool_spec_list, validate_args)
from tezdak.tools_ext.config import DEFAULT_CONFIG, load_config, make_executor, registry_from_config
from tezdak.tools_ext.defs import TOOL_DEFS, schema_for
from tezdak.tools_ext.executor import ToolCallError, call_with_tool_v1
from tezdak.tools_ext.registry import describe
from tezdak.tools_ext.stats import CallStats


class FakeOrders:
    def __init__(self):
        self.rows = {"TZ1001": {"awb": "TZ1001", "seller": "Zari", "address_text": "12 MG Road Pune"}}
        self.log = []

    def get(self, awb):
        return self.rows.get(awb)

    def update_address(self, awb, new_text, by):
        self.rows[awb]["address_text"] = new_text
        self.log.append(("update", awb, new_text, by))

    def cancel(self, awb, by):
        self.log.append(("cancel", awb, by))


class FakeTickets:
    def __init__(self):
        self.items = []
        self.notes = []

    def create(self, awb, kind, summary, priority="normal", source="chat"):
        self.items.append((awb, kind, summary, priority, source))
        return len(self.items)

    def add_note(self, tid, text, author):
        self.notes.append((tid, text, author))


class FakeCustomers:
    def get_by_phone(self, phone):
        return {"phone": phone, "name": "Asha", "language": "hinglish"} if phone.endswith("1234") else None


class FakeEvents:
    def __init__(self):
        self.out = []

    def publish(self, topic, payload):
        self.out.append((topic, payload))


class FakeBackend:
    def __init__(self):
        self.orders, self.tickets = FakeOrders(), FakeTickets()
        self.customers, self.events = FakeCustomers(), FakeEvents()


class SchemaTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        s = schema_for("create_ticket")
        validate_args({"awb": "TZ1001", "kind": "address", "summary": "wrong pin"}, s)
        with self.assertRaises(SchemaError) as cm:
            validate_args({"awb": "TZ1001", "kind": "x", "priority": "urgent", "extra": 1}, s)
        text = str(cm.exception)
        self.assertIn("summary", text)
        self.assertIn("priority", text)
        self.assertIn("extra", text)

    def test_types_and_bounds(self):
        s = schema_for("add_ticket_note")
        with self.assertRaises(SchemaError):
            validate_args({"ticket_id": True, "text": "hi"}, s)
        with self.assertRaises(SchemaError):
            validate_args({"ticket_id": 0, "text": "hi"}, s)

    def test_specs_shape(self):
        specs = tool_spec_list()
        self.assertEqual(len(specs), 7)
        self.assertEqual({s["name"] for s in specs}, set(TOOL_DEFS))
        specs[0]["name"] = "mutated"
        self.assertNotEqual(tool_spec_list()[0]["name"], "mutated")


class RegistryTests(unittest.TestCase):
    def test_defaults_uniform(self):
        reg = ToolRegistry.default()
        for name in reg.names():
            self.assertEqual((reg.get(name).timeout_s, reg.get(name).retries), (8, 2))
        self.assertEqual(reg.missing_defs(), [])
        self.assertIn("cancel_order", reg.writes())
        self.assertIn("get_order", reg.reads())
        self.assertIn("get_order", describe(reg))

    def test_overrides_skip_stale(self):
        reg = ToolRegistry.default({"get_order": {"timeout_s": 3}, "send_sms": {"retries": 0}})
        self.assertEqual(reg.get("get_order").timeout_s, 3)
        self.assertEqual(reg.ignored, ["send_sms"])
        with self.assertRaises(KeyError):
            reg.get("send_sms")


class ConfigTests(unittest.TestCase):
    def test_default_config_skips_stale(self):
        reg = registry_from_config(DEFAULT_CONFIG)
        self.assertEqual(sorted(reg.ignored), ["get_pickup_slots", "lookup_awb_v0", "send_sms"])
        self.assertEqual(reg.get("get_order").cache_ttl_s, 30)

    def test_file_and_env(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.json")
            with open(p, "w") as fh:
                json.dump({"tools": {"get_customer": {"cache_ttl_s": 5}}}, fh)
            cfg = load_config(p, environ={"TEZDAK_TOOLX_TIMEOUT_S": "2.5", "TEZDAK_TOOLX_USE_CACHE": "off"})
        self.assertEqual(cfg["timeout_s"], 2.5)
        self.assertFalse(cfg["use_cache"])
        reg = registry_from_config(cfg)
        self.assertEqual(reg.get("get_order").timeout_s, 2.5)
        self.assertEqual(reg.get("get_customer").cache_ttl_s, 5)


class CacheTests(unittest.TestCase):
    def test_ttl_expiry_and_invalidate(self):
        now = [0.0]
        c = TTLCache(clock=lambda: now[0])
        c.put("get_order", {"awb": "A"}, {"v": 1}, 10)
        self.assertEqual(c.get("get_order", {"awb": "A"}), {"v": 1})
        now[0] = 11
        self.assertIsNone(c.get("get_order", {"awb": "A"}))
        c.put("get_order", {"awb": "A"}, {"v": 2}, 10)
        c.invalidate_tool("get_order")
        self.assertEqual(len(c), 0)
        c.put("x", {}, 1, 0)
        self.assertEqual(len(c), 0)

    def test_eviction(self):
        c = TTLCache(max_entries=2)
        for i in range(5):
            c.put("t", {"i": i}, i, 100)
        self.assertLessEqual(len(c), 2)


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.be = FakeBackend()
        self.stats = CallStats()
        self.ex = make_executor(self.be, on_event=self.stats.on_event)

    def tearDown(self):
        self.ex.close()

    def test_get_order_cached(self):
        a = self.ex.call("get_order", {"awb": "TZ1001"})
        self.be.orders.rows["TZ1001"]["seller"] = "Changed"
        b = self.ex.call("get_order", {"awb": "TZ1001"})
        self.assertEqual(a, b)
        self.assertEqual(self.stats.summary()["cache_hits"], 1)

    def test_write_invalidates_read_cache(self):
        self.ex.call("get_order", {"awb": "TZ1001"})
        out = self.ex.call("update_address", {"awb": "TZ1001", "new_address": "44 Baner Road, Pune 411045"})
        self.assertEqual(out, {"ok": True, "awb": "TZ1001"})
        fresh = self.ex.call("get_order", {"awb": "TZ1001"})
        self.assertIn("Baner", fresh["order"]["address_text"])

    def test_tickets_and_notes(self):
        t = self.ex.call("create_ticket", {"awb": "TZ1001", "kind": "address", "summary": "needs change"})
        self.assertEqual(t, {"ticket_id": 1})
        self.assertEqual(self.ex.call("add_ticket_note", {"ticket_id": 1, "text": "called"})["ok"], True)
        self.assertEqual(self.be.tickets.notes[0], (1, "called", "agent"))

    def test_customer_and_template(self):
        self.assertEqual(self.ex.call("get_customer", {"phone": "9800001234"})["customer"]["name"], "Asha")
        self.assertEqual(self.ex.call("get_customer", {"phone": "9800009999"})["error"], "CUSTOMER_NOT_FOUND")
        r = self.ex.call("send_template_message", {"phone": "9800001234", "template": "delay_notice"})
        self.assertTrue(r["queued"])
        self.assertEqual(self.be.events.out[0][0], "template_message")

    def test_errors(self):
        self.assertEqual(self.ex.call("nope", {})["error"], "UNKNOWN_TOOL")
        self.assertEqual(self.ex.call("get_order", {})["error"], "BAD_ARGS")
        self.assertEqual(self.ex.call("get_order", {"awb": "ZZZ999"})["error"], "ORDER_NOT_FOUND")
        self.assertEqual(self.ex.call("cancel_order", {"awb": "ZZZ999"})["error"], "ORDER_NOT_FOUND")
        self.assertEqual(call_with_tool_v1(self.ex, "get_order", awb="ZZZ999")["error"], "ORDER_NOT_FOUND")

    def test_raise_errors_mode(self):
        ex = Executor(ToolRegistry.default(), build_handlers(self.be), raise_errors=True)
        with self.assertRaises(ToolCallError) as cm:
            ex.call("get_order", {})
        self.assertEqual(cm.exception.code, "BAD_ARGS")
        ex.close()

    def test_handler_exception(self):
        def boom(args):
            raise RuntimeError("db down")
        ex = Executor(ToolRegistry.default(), {"get_order": boom})
        self.assertEqual(ex.call("get_order", {"awb": "TZ1001"})["error"], "HANDLER_ERROR")
        ex.close()


class TimeoutTests(unittest.TestCase):
    def test_slow_handler_times_out_after_configured_attempts(self):
        calls = []
        lock = threading.Lock()

        def slow(args):
            with lock:
                calls.append(1)
            time.sleep(0.2)
            return {"ok": True}

        reg = ToolRegistry.default({"cancel_order": {"timeout_s": 0.02, "retries": 1}})
        events = []
        ex = Executor(reg, {"cancel_order": slow}, on_event=lambda k, d: events.append(k))
        out = ex.call("cancel_order", {"awb": "TZ1001"})
        self.assertEqual(out["error"], "TIMEOUT")
        self.assertEqual(out["attempts"], 2)
        self.assertEqual(events.count("tool_timeout"), 2)
        ex.close()

    def test_succeeds_after_first_slow_attempt(self):
        state = {"n": 0}

        def flaky(args):
            state["n"] += 1
            if state["n"] == 1:
                time.sleep(0.15)
            return {"order": {"awb": args["awb"]}}

        reg = ToolRegistry.default({"get_order": {"timeout_s": 0.03}})
        ex = Executor(reg, {"get_order": flaky}, backoff_s=0.001)
        self.assertEqual(ex.call("get_order", {"awb": "TZ1001"})["order"]["awb"], "TZ1001")
        ex.close()


if __name__ == "__main__":
    unittest.main()
