import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tezdak.policy.eligibility import refund_eligibility  # noqa: E402
from tezdak.policy.goodwill import goodwill_allowed, goodwill_needs_human  # noqa: E402
from tezdak.policy.loader import load_policy  # noqa: E402


def ship(**kw):
    base = {"status": "DELIVERED", "payment_mode": "PREPAID", "amount_inr": 1000, "attempts_used": 1}
    base.update(kw)
    return base


class Eligibility(unittest.TestCase):
    def test_within_policy(self):
        d = refund_eligibility(ship(), {"amount_inr": 1000, "days_since_delivery": 2}, load_policy("v2"))
        self.assertTrue(d.allowed)
        self.assertFalse(d.needs_human)
        self.assertEqual((d.window_days, d.limit_inr), (7, 5000))

    def test_outside_window(self):
        d = refund_eligibility(ship(), {"amount_inr": 500, "days_since_delivery": 6}, load_policy("v1"))
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "outside_window")

    def test_above_limit_needs_human(self):
        claim = {"amount_inr": 2500, "days_since_delivery": 1}
        self.assertTrue(refund_eligibility(ship(), claim, load_policy("v1")).needs_human)
        self.assertFalse(refund_eligibility(ship(), claim, load_policy("v2")).needs_human)

    def test_cod_manual_in_v1(self):
        d = refund_eligibility(ship(payment_mode="COD"), {"amount_inr": 300, "days_since_delivery": 1}, load_policy("v1"))
        self.assertTrue(d.allowed and d.needs_human)
        self.assertEqual(d.reason, "cod_manual_only")

    def test_v3_category_limit(self):
        claim = {"amount_inr": 1600, "days_since_delivery": 1, "category": "apparel"}
        self.assertTrue(refund_eligibility(ship(), claim, load_policy("v3")).needs_human)
        claim["category"] = "electronics"
        self.assertFalse(refund_eligibility(ship(), claim, load_policy("v3")).needs_human)

    def test_v3_hub_override(self):
        claim = {"amount_inr": 500, "days_since_delivery": 12}
        d = refund_eligibility(ship(attempts_used=3, status="NDR"), claim, load_policy("v3"))
        self.assertTrue(d.allowed and d.needs_human)
        self.assertIn("hub_override", d.notes)
        d = refund_eligibility(ship(attempts_used=2), claim, load_policy("v3"))
        self.assertFalse(d.allowed)

    def test_bad_inputs(self):
        p = load_policy("v2")
        self.assertEqual(refund_eligibility(ship(), {"amount_inr": 0}, p).reason, "amount_not_positive")
        self.assertEqual(refund_eligibility(ship(status="IN_TRANSIT"), {"amount_inr": 5}, p).reason,
                         "status_not_refundable")

    def test_claim_amount_falls_back_to_shipment(self):
        d = refund_eligibility(ship(amount_inr=2600), {"days_since_delivery": 1}, load_policy("v1"))
        self.assertTrue(d.needs_human)


class Goodwill(unittest.TestCase):
    def test_v1_once_only(self):
        p = load_policy("v1")
        self.assertTrue(goodwill_allowed(p, 100, []).allowed)
        d = goodwill_allowed(p, 100, [{"amount_inr": 100, "days_ago": 200}])
        self.assertFalse(d.allowed)
        self.assertEqual(d.reason, "already_received_once")

    def test_v3_rolling_cap(self):
        p = load_policy("v3")
        self.assertEqual(goodwill_allowed(p, 60, [{"amount_inr": 50, "days_ago": 10}]).reason, "exceeds_rolling_cap")
        self.assertTrue(goodwill_allowed(p, 50, [{"amount_inr": 50, "days_ago": 10}]).allowed)
        self.assertTrue(goodwill_allowed(p, 100, [{"amount_inr": 100, "days_ago": 45}]).allowed)
        self.assertEqual(goodwill_allowed(p, 10, [{"amount_inr": 100, "days_ago": 5}]).reason, "rolling_cap_reached")

    def test_v2_cap_and_bad_amount(self):
        p = load_policy("v2")
        self.assertFalse(goodwill_allowed(p, 250).allowed)
        self.assertTrue(goodwill_allowed(p, 150).allowed)
        self.assertFalse(goodwill_allowed(p, 0).allowed)

    def test_needs_human(self):
        self.assertTrue(goodwill_needs_human(load_policy("v1"), 2500))
        self.assertFalse(goodwill_needs_human(load_policy("v2"), 2500))


if __name__ == "__main__":
    unittest.main()
