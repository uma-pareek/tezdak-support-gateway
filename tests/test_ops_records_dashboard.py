import tempfile
import unittest
import warnings
from pathlib import Path

import _ops_fixtures as X

from tezdak.metrics import Metrics
from tezdak.ops import costs
from tezdak.ops.dashboard import Dashboard, build_dashboard, format_dashboard, percentile
from tezdak.ops.records import (ConversationRecord, load_records, read_records_jsonl, read_trace_dir,
                                record_from_events, write_records_jsonl)

SPECS = [
    dict(scenario="a", closed=True),
    dict(scenario="b", closed=True, escalated=True),
    dict(scenario="c"),
    dict(scenario="d", closed=True, text="My order shows delivered but I never got it"),
]


class RecordTests(unittest.TestCase):
    def test_fold_events(self):
        rec = record_from_events(X.make_events(closed=True, reply_after_s=3))
        self.assertTrue(rec.closed)
        self.assertFalse(rec.escalated)
        self.assertEqual(rec.turns, 1)
        self.assertEqual(rec.latencies_ms, [3000])
        self.assertEqual((rec.input_tokens, rec.cached_tokens, rec.output_tokens, rec.llm_calls), (1000, 200, 100, 2))
        self.assertEqual(rec.tool_counts, {"get_shipment": 1})
        self.assertEqual(rec.awb, "TZ4829301")

    def test_metadata_overrides(self):
        rec = record_from_events(X.make_events(), {"language": "en", "payment_mode": "COD", "pincode": "400001",
                                                   "tier": "metro", "channel": "whatsapp"})
        self.assertEqual((rec.language, rec.payment_mode, rec.pincode, rec.tier, rec.channel),
                         ("en", "COD", "400001", "metro", "whatsapp"))

    def test_empty_trace_rejected(self):
        with self.assertRaises(ValueError):
            record_from_events([])

    def test_jsonl_roundtrip(self):
        recs = [record_from_events(X.make_events(**s)) for s in SPECS]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.jsonl"
            write_records_jsonl(recs, path)
            self.assertEqual(read_records_jsonl(path), recs)

    def test_bad_schema_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "r.jsonl"
            path.write_text('{"scenario": "x"}\n')
            with self.assertRaises(ValueError):
                read_records_jsonl(path)

    def test_read_dir_and_deprecated_alias(self):
        with tempfile.TemporaryDirectory() as d:
            X.write_fixture_dir(d, SPECS)
            self.assertEqual(len(read_trace_dir(d)), 4)
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                self.assertEqual(len(load_records(d)), 4)
            self.assertTrue(any(issubclass(x.category, DeprecationWarning) for x in w))


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.records = [record_from_events(X.make_events(**s)) for s in SPECS]

    def test_resolved_rate_is_closed_without_escalation_over_all(self):
        dash = build_dashboard(self.records)
        self.assertEqual(dash.conversations, 4)
        self.assertEqual(dash.closed_without_escalation, 2)
        self.assertAlmostEqual(dash.resolved_rate, 0.5)
        self.assertAlmostEqual(dash.escalation_rate, 0.25)

    def test_matches_base_metrics_exactly(self):
        metrics = Metrics()
        for r in self.records:
            metrics.record(type("T", (), {"intent": r.intent, "escalated": r.escalated, "closed": r.closed})())
        dash = build_dashboard(self.records)
        self.assertEqual(dash.resolved_rate, metrics.resolved_rate)
        self.assertEqual(dash.escalation_rate, metrics.escalation_rate)
        self.assertEqual(dash.by_intent, metrics.by_intent)
        self.assertEqual(Dashboard.from_metrics(metrics).resolved_rate, metrics.resolved_rate)

    def test_open_conversation_is_not_resolved(self):
        dash = build_dashboard([record_from_events(X.make_events())])
        self.assertEqual(dash.resolved_rate, 0.0)

    def test_empty(self):
        dash = build_dashboard([])
        self.assertEqual((dash.resolved_rate, dash.escalation_rate, dash.latency_p50_ms), (0.0, 0.0, 0.0))
        self.assertEqual(dash.intent_mix, {})

    def test_latency_percentiles(self):
        self.assertEqual(percentile([], 50), 0.0)
        self.assertEqual(percentile(list(range(1, 101)), 90), 90.0)
        self.assertEqual(percentile([5], 99), 5.0)
        recs = [record_from_events(X.make_events(scenario=f"x{i}", reply_after_s=i)) for i in range(1, 11)]
        dash = build_dashboard(recs)
        self.assertEqual(dash.latency_p50_ms, 5000.0)
        self.assertEqual(dash.latency_p90_ms, 9000.0)

    def test_token_spend(self):
        dash = build_dashboard(self.records)
        self.assertEqual(dash.input_tokens, 4000)
        expected = 4 * (800 * 0.10 + 200 * 0.01 + 100 * 0.50) / 1e6
        self.assertAlmostEqual(dash.spend_usd, expected)
        self.assertAlmostEqual(dash.spend_usd, costs.total_cost_usd(self.records))

    def test_single_resolved_number(self):
        keys = [k for k in build_dashboard(self.records).to_dict() if k.startswith("resolved")]
        self.assertEqual(keys, ["resolved_rate"])

    def test_format(self):
        text = format_dashboard(build_dashboard(self.records))
        self.assertIn("resolved_rate: 50.0%", text)
        self.assertIn("escalation_rate: 25.0%", text)


@unittest.skipUnless(X.sim_available(), "carrier_sim not importable (set PYTHONPATH=<R>/private)")
class RealTraceTests(unittest.TestCase):
    def test_real_traces_produce_dashboard(self):
        with tempfile.TemporaryDirectory() as d:
            traces = X.run_real_traces(Path(d) / "run")
            recs = read_trace_dir(traces, X.DEV)
            self.assertEqual(len(recs), 6)
            dash = build_dashboard(recs)
            self.assertEqual(dash.conversations, 6)
            self.assertGreater(dash.input_tokens, 0)
            self.assertTrue(all(r.payment_mode in ("PREPAID", "COD") for r in recs))
            self.assertLessEqual(dash.closed_without_escalation, dash.closed)


if __name__ == "__main__":
    unittest.main()
