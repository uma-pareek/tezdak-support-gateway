import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tezdak.policy.v1_legacy import PolicyV1  # noqa: E402
from tezdak.policy.v2_table import PolicyV2  # noqa: E402
from tezdak.policy.v3_memo import PolicyV3  # noqa: E402
from tezdak.policy.loader import load_policy, available  # noqa: E402
from tezdak.policy.compare import compare_policies, compare_all, format_diff  # noqa: E402


class GenerationNumbers(unittest.TestCase):
    def test_v1_values(self):
        p = PolicyV1()
        self.assertEqual((p.window_days({}), p.limit_inr({})), (5, 2000))
        self.assertTrue(p.cod_refund_manual_only())
        self.assertTrue(p.goodwill_per_customer_once)

    def test_v2_defaults_and_overrides(self):
        p = PolicyV2()
        self.assertEqual((p.window_days({}), p.limit_inr({})), (7, 5000))
        self.assertEqual(p.window_days({"category": "grocery"}), 2)
        self.assertEqual(p.window_days({"seller": "SELLER-FASHIONKART"}), 10)
        self.assertEqual(p.limit_inr({"seller": "SELLER-GADGETHUB"}), 8000)
        self.assertEqual(p.limit_inr({"seller": "SELLER-BULKMART", "category": "books"}), 3000)

    def test_v3_limits_by_category(self):
        p = PolicyV3()
        got = {c: p.limit_inr({"category": c}) for c in ("electronics", "apparel", "grocery", "toys")}
        self.assertEqual(got, {"electronics": 3000, "apparel": 1500, "grocery": 800, "toys": 2000})

    def test_v3_window_by_payment_mode(self):
        p = PolicyV3()
        self.assertEqual(p.window_days({"payment_mode": "PREPAID"}), 10)
        self.assertEqual(p.window_days({"payment_mode": "COD"}), 7)

    def test_v3_hub_override_needs_attempt_three(self):
        p = PolicyV3()
        self.assertFalse(p.hub_override({"attempts_used": 2}))
        self.assertTrue(p.hub_override({"attempts_used": 3}))
        self.assertFalse(PolicyV3(hub_override_enabled=False).hub_override({"attempts_used": 3}))

    def test_describe(self):
        for p in (PolicyV1(), PolicyV2(), PolicyV3()):
            self.assertEqual(p.describe()["name"], p.name)


class Loader(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("TEZDAK_POLICY_GEN", None)

    def tearDown(self):
        os.environ.pop("TEZDAK_POLICY_GEN", None)
        if self._old is not None:
            os.environ["TEZDAK_POLICY_GEN"] = self._old

    def test_default_is_v2(self):
        self.assertEqual(load_policy().name, "v2")

    def test_env_selects(self):
        os.environ["TEZDAK_POLICY_GEN"] = "v3"
        self.assertEqual(load_policy().name, "v3")

    def test_explicit_name_beats_env_and_alias(self):
        os.environ["TEZDAK_POLICY_GEN"] = "v3"
        self.assertEqual(load_policy("legacy").name, "v1")

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            load_policy("v9")

    def test_available(self):
        self.assertEqual(available(), ["v1", "v2", "v3"])


class Compare(unittest.TestCase):
    SHIP = {"status": "DELIVERED", "payment_mode": "PREPAID", "amount_inr": 1800, "attempts_used": 1}

    def test_window_day_six_differs(self):
        claim = {"amount_inr": 1800, "days_since_delivery": 6}
        r = compare_policies(self.SHIP, claim, "v1", "v2")
        self.assertFalse(r["decision_a"].allowed)
        self.assertTrue(r["decision_b"].allowed)
        self.assertIn("allowed", r["diff"])
        self.assertIn("v1 vs v2", format_diff(r))

    def test_agreement(self):
        r = compare_policies(self.SHIP, {"amount_inr": 100, "days_since_delivery": 1}, "v2", "v2")
        self.assertEqual(r["diff"], {})
        self.assertIn("agree", format_diff(r))

    def test_compare_all_three(self):
        out = compare_all(self.SHIP, {"amount_inr": 1800, "days_since_delivery": 8})
        self.assertEqual(sorted(out), ["v1", "v2", "v3"])
        self.assertEqual([out[k].allowed for k in ("v1", "v2", "v3")], [False, False, True])


if __name__ == "__main__":
    unittest.main()
