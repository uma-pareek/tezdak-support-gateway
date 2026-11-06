"""The run report lists facts per chat. These tests use a fake carrier and a fake agent instead of the simulator."""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import _eval_helpers  # noqa: F401  (puts the repo root on sys.path)
from eval.report import build_report, llm_line, render_markdown, scenario_facts, scenario_line, tool_calls_from_trace
from eval.run_eval import run_dir, run_scenario
from eval.trace import Trace

SCENARIO = {
    "id": "fake-1",
    "world": {"now": "2026-11-02T09:30:00+05:30", "shipment": {"awb": "TZ1000001"}},
    "customer": {"card": {}, "script": {"opening": "where is my parcel", "rules": [], "fallback": "ok thanks",
                                         "max_turns": 2}},
}


class FakeCarrier:
    def __init__(self, scenario):
        self.now = datetime.fromisoformat(scenario["world"]["now"])
        self._ledger = []
        self._attempts = 1

    def _log(self, type_, awb, args, result):
        self._ledger.append({"seq": len(self._ledger) + 1, "ts": self.now.isoformat(), "type": type_, "awb": awb,
                             "args": args, "result": result})

    def get_shipment(self, awb, timeout_s=8.0):
        self.now += timedelta(seconds=1)
        return {"awb": awb, "status": "NDR", "attempts_used": self._attempts}

    def reschedule(self, awb, slot, timeout_s=8.0):
        self._attempts += 1
        self._log("reschedule_applied", awb, {"slot": slot}, {"status": "ok", "attempts_used": self._attempts})
        return {"status": "ok"}

    def create_refund(self, awb, amount_inr, kind, vpa=None, timeout_s=8.0):
        result = {"mode": "wallet", "amount_inr": amount_inr, "kind": kind}
        self._log("refund_issued", awb, {"amount_inr": amount_inr, "kind": kind, "vpa": vpa}, result)
        return result

    def close(self, awb, resolution):
        self._log("closed", awb, {"resolution": resolution}, {"status": "closed"})
        return {"status": "closed"}

    def ledger(self):
        return list(self._ledger)

    def outcome(self):
        return {"attempts_used": self._attempts}


class FakeLLM:
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "calls": 0}


class FakeAgent:
    """Reads the shipment, books a slot, pays goodwill and closes."""

    def __init__(self, carrier):
        self.carrier = carrier
        self.llm = FakeLLM()
        self.llm.usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "calls": 0}

    def handle(self, conversation):
        awb = self.carrier.awb
        self.carrier.get_shipment(awb)
        if len(conversation) == 1:
            self.carrier.reschedule(awb, "tomorrow")
            self.carrier.create_refund(awb, 50, "goodwill")
        else:
            self.carrier.close(awb, "done")
        self.llm.usage = {"input_tokens": 1000, "cached_tokens": 200, "output_tokens": 100,
                          "calls": self.llm.usage["calls"] + 1}
        return {"text": "Booked for tomorrow."}


class FactsTests(unittest.TestCase):
    def run_fake(self):
        return run_scenario(SCENARIO, FakeAgent, carrier_factory=FakeCarrier)

    def test_facts_of_one_chat(self):
        f = self.run_fake().facts
        self.assertEqual(f["id"], "fake-1")
        self.assertEqual(f["customer_turns"], 2)
        self.assertEqual([c["name"] for c in f["tool_calls"]],
                         ["get_shipment", "reschedule", "create_refund", "get_shipment", "close"])
        self.assertEqual(f["bookings"], 1)
        self.assertEqual(f["refunds"], [{"amount_inr": 50, "kind": "goodwill", "mode": "wallet"}])
        self.assertEqual(f["refunds_paid_inr"], 50)
        self.assertFalse(f["escalated"])
        self.assertTrue(f["closed"])
        self.assertEqual(f["attempts_used"], 2)
        self.assertEqual(f["ledger_by_type"], {"closed": 1, "refund_issued": 1, "reschedule_applied": 1})
        self.assertEqual(f["llm"]["calls"], 2)
        self.assertIsNone(f["error"])

    def test_timeout_event_marks_its_call(self):
        tr = Trace("s", clock=lambda: "t")
        tr.add("tool_call", {"name": "get_scans", "args": {"awb": "TZ1"}, "attempt": 0})
        tr.add("tool_timeout", {"name": "get_scans", "args": {"awb": "TZ1"}, "attempt": 0, "timeout_s": 1})
        tr.add("tool_call", {"name": "get_scans", "args": {"awb": "TZ1"}, "attempt": 1})
        calls = tool_calls_from_trace(tr.events)
        self.assertEqual([(c["attempt"], c["timed_out"]) for c in calls], [(0, True), (1, False)])

    def test_ledger_without_flags_is_traced(self):
        res = self.run_fake()
        ledger_events = [e for e in res.trace if e["kind"] == "ledger"]
        self.assertEqual(len(ledger_events), 3)
        self.assertNotIn("flags", ledger_events[0]["data"])

    def test_long_args_are_shortened(self):
        tr = Trace("s", clock=lambda: "t")
        tr.add("tool_call", {"name": "close", "args": {"resolution": "x" * 500}, "attempt": 0})
        calls = tool_calls_from_trace(tr.events)
        self.assertLessEqual(len(calls[0]["args"]["resolution"]), 80)

    def test_report_lists_each_chat(self):
        a, b = self.run_fake().facts, self.run_fake().facts
        usage = {"calls": 4, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}
        with tempfile.TemporaryDirectory() as d:
            rep = build_report("two", [a, b], usage, Path(d) / "none", Path(d) / "runs" / "two")
        self.assertNotIn("totals", rep)
        self.assertEqual([f["bookings"] for f in rep["scenarios"]], [1, 1])
        self.assertEqual([f["refunds_paid_inr"] for f in rep["scenarios"]], [50, 50])
        md = render_markdown(rep)
        for gone in ("Chats escalated", "chats closed", "Bookings:", "paid)", "errors:"):
            self.assertNotIn(gone, md)
        self.assertEqual(md.count("| fake-1 |"), 2)
        self.assertTrue(llm_line(rep).startswith("LLM calls 4,"), llm_line(rep))

    def test_error_is_recorded(self):
        class Broken(FakeAgent):
            def handle(self, conversation):
                raise RuntimeError("boom")
        res = run_scenario(SCENARIO, Broken, carrier_factory=FakeCarrier)
        self.assertEqual(res.facts["error"], "RuntimeError: boom")
        self.assertIn("error: RuntimeError: boom", scenario_line(res.facts))

    def test_scenario_facts_without_outcome(self):
        f = scenario_facts("x", [], [], None, {"calls": 0})
        self.assertIsNone(f["attempts_used"])
        self.assertEqual(f["bookings"], 0)

    def test_run_dir_writes_report_and_traces(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "scen"
            src.mkdir()
            (src / "fake-1.json").write_text(json.dumps(SCENARIO), encoding="utf-8")
            out = Path(d) / "runs" / "one"
            rep = run_dir(src, out, agent_factory=FakeAgent, carrier_factory=FakeCarrier)
            self.assertEqual(len(rep["scenarios"]), 1)
            self.assertNotIn("totals", rep)
            self.assertTrue((out / "traces" / "fake-1.jsonl").exists())
            self.assertIn("| fake-1 |", (out / "report.md").read_text(encoding="utf-8"))
            again = run_dir(src, Path(d) / "runs" / "two", agent_factory=FakeAgent, carrier_factory=FakeCarrier)
            self.assertEqual(again["previous_run"], "one")
            self.assertEqual(again["diff_vs_previous"], [])


if __name__ == "__main__":
    unittest.main()
