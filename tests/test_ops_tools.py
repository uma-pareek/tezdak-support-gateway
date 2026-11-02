import io
import tempfile
import unittest
from datetime import date
from pathlib import Path

import _ops_fixtures as X

from eval.trace import read_trace, write_trace
from tezdak.ops import admin_cli, alerts, cohorts, costs, reports, retention, sampling, shadow_eval
from tezdak.ops.dashboard import build_dashboard
from tezdak.ops.records import read_trace_dir, record_from_events

SPECS = [
    dict(scenario="a", closed=True, day="2026-11-02"),
    dict(scenario="b", closed=True, escalated=True, day="2026-11-02"),
    dict(scenario="c", day="2026-11-03"),
    dict(scenario="d", closed=True, day="2026-11-09", text="Order shows delivered, never got it", awb="TZ5550001"),
    dict(scenario="e", closed=True, escalated=True, day="2026-11-09", awb="TZ5550002"),
    dict(scenario="f", escalated=True, day="2026-11-09", awb="TZ5550003"),
]
META = {
    "a": dict(channel="whatsapp", language="hinglish", payment_mode="COD", tier="metro", pincode="110017"),
    "b": dict(channel="whatsapp", language="en", payment_mode="PREPAID", tier="tier2", pincode="302001"),
    "c": dict(channel="app", language="en", payment_mode="PREPAID", pincode="400001"),
}


def recs(specs=SPECS, meta=META):
    return [record_from_events(X.make_events(**s), meta.get(s["scenario"])) for s in specs]


class CostTests(unittest.TestCase):
    def test_rates(self):
        self.assertAlmostEqual(costs.spend_usd(1_000_000, 0, 0), 0.10)
        self.assertAlmostEqual(costs.spend_usd(1_000_000, 1_000_000, 0), 0.01)
        self.assertAlmostEqual(costs.spend_usd(0, 0, 1_000_000), 0.50)

    def test_matches_eval_report_formula(self):
        from eval.report import spend_usd as base
        usage = {"input_tokens": 6258, "cached_tokens": 875, "output_tokens": 317}
        self.assertAlmostEqual(costs.spend_usd(6258, 875, 317), base(usage))

    def test_helpers(self):
        r = recs()
        self.assertEqual(costs.token_totals(r)["calls"], 12)
        self.assertAlmostEqual(costs.cache_hit_ratio(r), 0.2)
        self.assertEqual(costs.cache_hit_ratio([]), 0.0)
        self.assertAlmostEqual(costs.cost_per_conversation(r) * 6, costs.total_cost_usd(r))
        self.assertEqual(set(costs.cost_by_intent(r)), {x.intent for x in r})
        self.assertAlmostEqual(costs.usd_to_inr(1.0, 80.0), 80.0)


class CohortTests(unittest.TestCase):
    def test_group_by_each_dimension(self):
        r = recs()
        self.assertEqual(sorted(cohorts.group_by(r, "channel")), ["app", "chat", "whatsapp"])
        self.assertEqual(len(cohorts.group_by(r, "payment_mode")["COD"]), 1)
        self.assertEqual(sorted(cohorts.group_by(r, "language")), sorted({x.language for x in r}))

    def test_pincode_tier_uses_tier_then_pincode_guess(self):
        tiers = cohorts.group_by(recs(), "pincode_tier")
        self.assertEqual(len(tiers["metro"]), 2)   # a by tier, c by 40 prefix
        self.assertEqual(len(tiers["tier2"]), 1)
        self.assertEqual(len(tiers["unknown"]), 3)

    def test_unknown_dimension(self):
        with self.assertRaises(ValueError):
            cohorts.group_by(recs(), "weather")

    def test_cohort_dashboards_and_text(self):
        dashes = cohorts.cohort_dashboards(recs(), "channel")
        self.assertEqual(dashes["whatsapp"].conversations, 2)
        self.assertAlmostEqual(dashes["whatsapp"].resolved_rate, 0.5)
        self.assertIn("cohorts by channel", cohorts.format_cohorts(recs(), "channel"))


class ReportTests(unittest.TestCase):
    def test_daily(self):
        text = reports.daily_report(recs(), date(2026, 11, 2))
        self.assertIn("2026-11-02", text)
        self.assertIn("conversations: 2", text)
        self.assertIn("No conversations", reports.daily_report(recs(), date(2026, 1, 1)))

    def test_weekly(self):
        text = reports.weekly_report(recs(), "2026-W45")
        self.assertIn("conversations: 3", text)
        self.assertIn("2026-11-03", text)
        self.assertIn("conversations: 3", reports.weekly_report(recs(), "2026-W46"))
        self.assertIn("No conversations", reports.weekly_report(recs(), "2026-W01"))

    def test_csv(self):
        text = reports.export_csv(recs())
        lines = text.strip().split("\n")
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0].split(",")[0], "scenario")

    def test_deprecated_format_report_uses_latest_day(self):
        self.assertIn("2026-11-09", reports.format_report(recs()))
        self.assertEqual(reports.format_report([]), "No conversations.")


class AlertTests(unittest.TestCase):
    def test_escalation_rate_rule_fires(self):
        dash = build_dashboard(recs())  # 3 of 6 escalated = 0.5
        fired = alerts.evaluate(dash)
        self.assertEqual([a.rule for a in fired], ["escalation_rate_high"])
        self.assertIn("escalation_rate", fired[0].text())

    def test_quiet_when_below_threshold(self):
        calm = [record_from_events(X.make_events(scenario=f"s{i}", closed=True)) for i in range(6)]
        self.assertEqual(alerts.evaluate(build_dashboard(calm)), [])
        self.assertEqual(alerts.format_alerts([]), "no alerts")

    def test_min_sample_guard(self):
        one = [record_from_events(X.make_events(escalated=True))]
        self.assertEqual(alerts.evaluate(build_dashboard(one)), [])

    def test_custom_rule_and_bad_op(self):
        dash = build_dashboard(recs())
        low = alerts.AlertRule("resolved_low", "resolved_rate", "lt", 0.9, min_sample=1)
        self.assertEqual(len(alerts.evaluate(dash, [low])), 1)
        with self.assertRaises(ValueError):
            alerts.AlertRule("x", "resolved_rate", "eq", 1).fires(dash)


class SamplingTests(unittest.TestCase):
    def test_random_sample_deterministic(self):
        r = recs()
        self.assertEqual([x.scenario for x in sampling.random_sample(r, 3)],
                         [x.scenario for x in sampling.random_sample(r, 3)])
        self.assertEqual(len(sampling.random_sample(r, 99)), 6)

    def test_stratified(self):
        picked = sampling.stratified_sample(recs(), 1)
        self.assertEqual(len({x.intent for x in picked}), len(picked))

    def test_escalated_first(self):
        picked = sampling.escalated_first(recs(), 4)
        self.assertEqual(len(picked), 4)
        self.assertEqual({x.scenario for x in picked[:3]}, {"b", "e", "f"})

    def test_pick_for_review_unique_and_bounded(self):
        ids = sampling.pick_for_review(recs(), 5)
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)
        self.assertEqual(sampling.pick_for_review([], 3), [])


class RetentionTests(unittest.TestCase):
    def test_redacts_phone_and_awb_consistently(self):
        red = retention.Redactor()
        out = red.redact_text("Call +91-90000-00001 about TZ4829301, again TZ4829301 and 9000000001")
        self.assertNotIn("TZ4829301", out)
        self.assertNotIn("90000", out)
        self.assertEqual(out.count("AWB-0001"), 2)
        self.assertEqual(out.count("PHONE-0001"), 2)

    def test_nested_values_and_flags(self):
        red = retention.Redactor(mask_phone=False)
        value = red.redact_value({"a": ["TZ1234567", {"b": "9000000001"}], "n": 5})
        self.assertEqual(value["a"][0], "AWB-0001")
        self.assertEqual(value["a"][1]["b"], "9000000001")
        self.assertEqual(value["n"], 5)

    def test_export_dir_leaves_no_pii(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = Path(d) / "src", Path(d) / "dst"
            X.write_fixture_dir(src, SPECS[:2])
            n = retention.export_redacted_dir(src, dst, read_trace, write_trace)
            self.assertEqual(n, 2)
            for p in dst.glob("*.jsonl"):
                self.assertFalse(retention.contains_pii(p.read_text()))

    def test_record_redaction(self):
        rec = record_from_events(X.make_events(), {"phone": "+91-90000-00001"})
        out = retention.Redactor().redact_record(rec)
        self.assertFalse(retention.contains_pii(out.awb + out.phone + out.first_text))


class ShadowEvalTests(unittest.TestCase):
    def test_compare(self):
        base = [record_from_events(X.make_events(scenario="a", closed=True)),
                record_from_events(X.make_events(scenario="b", escalated=True)),
                record_from_events(X.make_events(scenario="only-base"))]
        other = [record_from_events(X.make_events(scenario="a", closed=True)),
                 record_from_events(X.make_events(scenario="b", closed=True)),
                 record_from_events(X.make_events(scenario="only-other"))]
        res = shadow_eval.compare(base, other)
        self.assertEqual(res["only_in_base"], ["only-base"])
        self.assertEqual(res["only_in_other"], ["only-other"])
        self.assertEqual(list(res["changed"]), ["b"])
        self.assertEqual(res["delta"], {"closed": 1, "escalated": -1})
        self.assertIn("scenarios with different actions: 1", shadow_eval.format_comparison(res))

    def test_identical_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            X.write_fixture_dir(a, SPECS)
            X.write_fixture_dir(b, SPECS)
            res = shadow_eval.compare_dirs(a, b)
            self.assertEqual((res["changed"], res["delta"]), ({}, {}))

    def test_tool_counts(self):
        r = recs()
        self.assertEqual(shadow_eval.tool_counts(r), {"get_shipment": 6})
        self.assertEqual(shadow_eval.tool_counts(r, writes_only=True), {})


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        code = admin_cli.main(argv, out)
        return code, out.getvalue()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.traces = Path(self.tmp.name) / "traces"
        X.write_fixture_dir(self.traces, SPECS)

    def test_summary(self):
        code, text = self.run_cli(["summary", "--traces", str(self.traces)])
        self.assertEqual(code, 0)
        self.assertIn("conversations: 6", text)
        self.assertIn("resolved_rate: 33.3%", text)
        self.assertIn("escalation_rate_high", text)

    def test_tail(self):
        code, text = self.run_cli(["tail", "--traces", str(self.traces), "-n", "2"])
        self.assertEqual(code, 0)
        self.assertEqual(len(text.strip().split("\n")), 2)

    def test_cohorts(self):
        code, text = self.run_cli(["cohorts", "--traces", str(self.traces), "--by", "channel"])
        self.assertEqual(code, 0)
        self.assertIn("chat", text)

    def test_export_csv_and_redacted(self):
        out_csv = Path(self.tmp.name) / "o.csv"
        code, _ = self.run_cli(["export", "--traces", str(self.traces), "--out", str(out_csv)])
        self.assertEqual(code, 0)
        self.assertEqual(len(out_csv.read_text().strip().split("\n")), 7)
        red = Path(self.tmp.name) / "red"
        code, text = self.run_cli(["export", "--traces", str(self.traces), "--out", str(red), "--format", "redacted"])
        self.assertEqual(code, 0)
        self.assertIn("6 redacted", text)

    def test_empty_dir_is_error(self):
        empty = Path(self.tmp.name) / "empty"
        empty.mkdir()
        self.assertEqual(admin_cli.main(["summary", "--traces", str(empty)], io.StringIO()), 1)

    def test_scenarios_metadata(self):
        code, text = self.run_cli(["cohorts", "--traces", str(self.traces), "--scenarios", str(X.DEV)])
        self.assertEqual(code, 0)


@unittest.skipUnless(X.sim_available(), "carrier_sim not importable (set PYTHONPATH=<R>/private)")
class RealTraceToolTests(unittest.TestCase):
    def test_pipeline_on_real_traces(self):
        with tempfile.TemporaryDirectory() as d:
            traces = X.run_real_traces(Path(d) / "run")
            records = read_trace_dir(traces, X.DEV)
            self.assertEqual(len(records), 6)
            self.assertEqual(cohorts.group_by(records, "payment_mode").keys() <= {"COD", "PREPAID"}, True)
            self.assertEqual(len(reports.export_csv(records).strip().split("\n")), 7)
            self.assertEqual(shadow_eval.compare_dirs(traces, traces)["changed"], {})
            red = Path(d) / "red"
            code = admin_cli.main(["export", "--traces", str(traces), "--out", str(red), "--format", "redacted"],
                                  io.StringIO())
            self.assertEqual(code, 0)
            for p in red.glob("*.jsonl"):
                self.assertFalse(retention.contains_pii(p.read_text()), p.name)
            self.assertEqual(admin_cli.main(["summary", "--traces", str(traces), "--scenarios", str(X.DEV)],
                                            io.StringIO()), 0)


if __name__ == "__main__":
    unittest.main()


class ExtrasTests(unittest.TestCase):
    def test_filter_and_merge(self):
        from tezdak.ops.records import filter_records, merge_record_sets, scenario_ids
        r = recs()
        self.assertEqual(scenario_ids(filter_records(r, since="2026-11-03", until="2026-11-09")), ["c"])
        self.assertEqual(scenario_ids(filter_records(r, escalated=True)), ["b", "e", "f"])
        self.assertEqual(scenario_ids(filter_records(r, channel="app")), ["c"])
        self.assertEqual(len(filter_records(r, intent="nope")), 0)
        self.assertEqual(len(merge_record_sets(r, r[:2])), 6)

    def test_dashboard_diff_and_markdown(self):
        from tezdak.ops.dashboard import diff_dashboards, intent_table, to_markdown
        r = recs()
        before, after = build_dashboard(r[:3]), build_dashboard(r)
        delta = diff_dashboards(before, after)
        self.assertEqual(delta["conversations"], 3)
        self.assertAlmostEqual(delta["escalation_rate"], 0.5 - 1 / 3)
        self.assertEqual(sum(c for _, c, _ in intent_table(after)), 6)
        self.assertIn("| resolved_rate | 33.3% |", to_markdown(after))

    def test_cost_helpers(self):
        r = recs()
        self.assertAlmostEqual(costs.project_monthly_usd(r, 1000), costs.cost_per_conversation(r) * 1000)
        self.assertTrue(costs.over_budget(r, 0.0))
        self.assertFalse(costs.over_budget(r, 1.0))
        self.assertEqual(len(costs.cost_table(r)), 6)

    def test_alert_state_cooldown(self):
        dash = build_dashboard(recs())
        state = alerts.AlertState(cooldown_runs=2)
        self.assertEqual(len(state.filter_new(alerts.evaluate(dash))), 1)
        self.assertEqual(state.filter_new(alerts.evaluate(dash)), [])
        self.assertEqual(len(state.filter_new(alerts.evaluate(dash))), 1)

    def test_report_rows_and_sheet(self):
        r = recs()
        rows = reports.by_day_rows(r)
        self.assertEqual([x[0] for x in rows], ["2026-11-02", "2026-11-03", "2026-11-09"])
        self.assertIn("| conversations | 6 |", reports.markdown_report(r))
        sheet = sampling.review_sheet_csv(r, ["a", "zzz"])
        self.assertEqual(len(sheet.strip().split("\n")), 2)
