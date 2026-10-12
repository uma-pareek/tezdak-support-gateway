import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feature_fakes import AWB, FakeBackend, FeatureCarrier, make_ctx  # noqa: E402

from tezdak.features import FeatureRegistry  # noqa: E402
from tezdak.features.base import Feature  # noqa: E402
from tezdak.features.config import FeatureConfig  # noqa: E402
from tezdak.features import extract  # noqa: E402
from tezdak.features.planner import FeaturePlanner, FeatureSet  # noqa: E402
from tezdak.features.templates import say, keys  # noqa: E402
from tezdak.features.usage import UsageLog  # noqa: E402


class RegistryTests(unittest.TestCase):
    def test_default_has_ten_features_and_unique_tools(self):
        reg = FeatureRegistry.default()
        self.assertEqual(len(reg.features), 10)
        names = [s["name"] for s in reg.all_specs()]
        self.assertEqual(len(names), len(set(names)))
        for s in reg.all_specs():
            self.assertEqual(s["type"], "function")
            self.assertIn("properties", s["parameters"])
            self.assertTrue(set(s["parameters"]["required"]) <= set(s["parameters"]["properties"]))

    def test_no_rider_dispute_tool_exposed(self):
        names = [s["name"] for s in FeatureRegistry.default().all_specs()]
        self.assertFalse([n for n in names if "dispute" in n])

    def test_for_context_by_intent(self):
        reg = FeatureRegistry.default()
        got = {f.name for f in reg.for_context(make_ctx(intent="wismo"))}
        self.assertIn("wismo_detail", got)
        self.assertNotIn("cancel_order", got)

    def test_dispatch_unknown_and_bug(self):
        reg = FeatureRegistry.default()
        ctx = make_ctx()
        self.assertEqual(reg.dispatch("nope", {}, ctx)["error"], "unknown_tool")

        class Bad(Feature):
            name = "bad"
            def tool_specs(self):
                return [{"type": "function", "name": "bad_tool", "description": "", "parameters": {"type": "object", "properties": {}, "required": []}}]
            def run_tool(self, name, args, ctx):
                raise ValueError("boom")
        r = FeatureRegistry([Bad()])
        self.assertEqual(r.dispatch("bad_tool", {}, ctx)["error"], "feature_failed")

    def test_duplicate_registration_rejected(self):
        reg = FeatureRegistry.default()
        with self.assertRaises(ValueError):
            reg.register(reg.features[0])


class ExtractTests(unittest.TestCase):
    def test_vpa_amount_rating_slot(self):
        self.assertEqual(extract.find_vpa("mera upi ravi.k@okaxis hai"), "ravi.k@okaxis")
        self.assertEqual(extract.find_amount("refund Rs 1,499 chahiye"), 1499)
        self.assertEqual(extract.find_amount("500 rupaye"), 500)
        self.assertEqual(extract.find_rating("4 star dena"), 4)
        self.assertEqual(extract.find_rating("paanch star"), 5)
        self.assertEqual(extract.find_slot("kal bhej do"), "tomorrow")
        self.assertEqual(extract.find_slot("2026-11-05 ko"), "2026-11-05")
        self.assertIsNone(extract.find_slot("whatever"))

    def test_address_and_prefill(self):
        t = "new address: 5 MG Road, Hazratganj, Lucknow 226001 for TZ4829301"
        self.assertTrue(extract.find_address(t).startswith("5 MG Road"))
        self.assertEqual(extract.prefill("address_update", t)["awb"], "TZ4829301")
        self.assertEqual(extract.prefill("rider_feedback", "3/5")["rating"], 3)


class PlannerTests(unittest.TestCase):
    def test_specs_capped_and_dispatch_guard(self):
        p = FeaturePlanner(config=FeatureConfig(max_specs=1))
        ctx = make_ctx(intent="reschedule_request", text="kal bhejo")
        self.assertEqual(len(p.specs(ctx)), 1)
        self.assertEqual(p.dispatch("cancel_customer_order", {"awb": AWB, "reason": "x"}, ctx)["error"], "tool_not_available")

    def test_disabled_feature_not_active(self):
        p = FeaturePlanner(config=FeatureConfig(disabled=("wismo_detail",)))
        self.assertNotIn("wismo_detail", [f.name for f in p.active(make_ctx(intent="wismo"))])

    def test_hint_block_and_usage(self):
        p = FeaturePlanner(config=FeatureConfig())
        ctx = make_ctx(carrier=FeatureCarrier("OUT_FOR_DELIVERY"), intent="wismo")
        self.assertIn("wismo_detail", p.hint_block(ctx))
        r = p.dispatch("wismo_detail", {"awb": AWB}, ctx)
        self.assertNotIn("error", r)
        self.assertEqual(p.usage.summary()["calls"], 1)

    def test_config_from_env(self):
        c = FeatureConfig.from_env({"TEZDAK_FEATURES_ENABLED": "handoff,cod_refund", "TEZDAK_FEATURES_MAX_SPECS": "x"})
        self.assertTrue(c.is_on("handoff"))
        self.assertFalse(c.is_on("slot_picker"))
        self.assertEqual(c.max_specs, 12)

    def test_deprecated_shim_warns(self):
        with self.assertWarns(DeprecationWarning):
            FeatureSet(config=FeatureConfig())

    def test_suggested_args(self):
        p = FeaturePlanner(config=FeatureConfig())
        ctx = make_ctx(intent="refund_status", text="refund 800 rupees to a.b@upi")
        self.assertEqual(p.suggested_args(ctx)["cod_refund"]["vpa"], "a.b@upi")


class SmallPartsTests(unittest.TestCase):
    def test_templates(self):
        for k in keys():
            self.assertTrue(say(k))
            self.assertTrue(say(k, "hinglish"))

    def test_usage_log_limit(self):
        log = UsageLog(limit=2)
        for i in range(4):
            log.record("t", "f", None, {"error": "e"} if i % 2 else {})
        self.assertEqual(len(log.entries), 2)
        self.assertEqual(log.summary()["errors"], 1)


if __name__ == "__main__":
    unittest.main()
