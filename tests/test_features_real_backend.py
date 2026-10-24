"""One check per feature against tezdak.backend.facade.Backend.in_memory(). Skipped if the backend is absent."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feature_fakes import AWB, FeatureCarrier, make_ctx  # noqa: E402

try:
    from tezdak.backend.facade import Backend
except Exception:  # backend package not present yet
    Backend = None

from tezdak.features import FeatureRegistry  # noqa: E402


@unittest.skipIf(Backend is None, "tezdak.backend not importable")
class RealBackendTests(unittest.TestCase):
    def setUp(self):
        self.be = Backend.in_memory()
        self.be.orders.put(AWB, "Nova Apparel", "apparel", ["kurta"], 1499, "12 Rose Lane, Lucknow 226016", "+91-90000-00001")
        self.reg = FeatureRegistry.default()

    def ctx(self, status="IN_TRANSIT", **kw):
        return make_ctx(carrier=FeatureCarrier(status, **kw), backend=self.be)

    def test_wismo(self):
        self.assertNotIn("error", self.reg.dispatch("wismo_detail", {"awb": AWB}, self.ctx()))

    def test_address(self):
        r = self.reg.dispatch("update_delivery_address", {"awb": AWB, "new_address": "9 New Road, Lucknow 226016"}, self.ctx())
        self.assertTrue(r["updated"], r)
        self.assertEqual(len(self.be.orders.address_history(AWB)), 1)

    def test_cancel(self):
        r = self.reg.dispatch("cancel_customer_order", {"awb": AWB, "reason": "changed mind"}, self.ctx())
        self.assertTrue(r["cancelled"], r)

    def test_cod_refund(self):
        r = self.reg.dispatch("cod_refund_payout", {"awb": AWB, "amount_inr": 500, "vpa": "a.b@upi"}, self.ctx("DELIVERED"))
        self.assertTrue(r["paid"], r)

    def test_feedback(self):
        r = self.reg.dispatch("save_rider_feedback", {"awb": AWB, "rating": 4, "comment": "ok"}, self.ctx())
        self.assertTrue(r["saved"], r)

    def test_slots(self):
        r = self.reg.dispatch("book_delivery_slot", {"awb": AWB, "slot": "tomorrow"}, self.ctx("NDR"))
        self.assertTrue(r["booked"], r)

    def test_delay(self):
        r = self.reg.dispatch("plan_delay_message", {"awb": AWB}, self.ctx("NDR"))
        self.assertTrue(r["delayed"], r)

    def test_promise(self):
        r = self.reg.dispatch("record_eta_promise", {"awb": AWB, "eta": "tomorrow"}, self.ctx())
        self.assertTrue(r["recorded"], r)
        r = self.reg.dispatch("check_promises", {"awb": AWB}, self.ctx())
        self.assertEqual(len(r["promises"]), 1, r)

    def test_handoff(self):
        r = self.reg.dispatch("create_handoff", {"awb": AWB, "reason": "customer_asked"}, self.ctx())
        self.assertTrue(r["created"], r)

    def test_not_received(self):
        r = self.reg.dispatch("not_received_next_question", {"awb": AWB}, self.ctx("DELIVERED"))
        self.assertEqual(r["ask"], "checked_neighbours", r)


if __name__ == "__main__":
    unittest.main()
