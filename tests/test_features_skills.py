import os
import sys
import unittest
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feature_fakes import AWB, NOW, FakeBackend, FeatureCarrier, make_ctx  # noqa: E402

from tezdak.features import (address_update, cancel_order, cod_refund, delay_notifier, handoff, not_received_helper,  # noqa: E402
                             promise_tracker, rider_feedback, slot_picker, wismo_detail)


def run(feature, tool, args, **kw):
    ctx = make_ctx(**kw)
    return feature.run_tool(tool, args, ctx), ctx


class WismoTests(unittest.TestCase):
    f = wismo_detail.WismoDetailFeature()

    def test_out_for_delivery(self):
        r, _ = run(self.f, "wismo_detail", {"awb": AWB}, carrier=FeatureCarrier("OUT_FOR_DELIVERY"))
        self.assertEqual(r["status"], "OUT_FOR_DELIVERY")
        self.assertEqual(r["eta_date"], NOW.date().isoformat())
        self.assertEqual(r["attempts_left"], 2)
        self.assertIn("out for delivery", r["summary"])

    def test_hinglish_and_delivered(self):
        r, _ = run(self.f, "wismo_detail", {}, carrier=FeatureCarrier("DELIVERED"), language="hinglish")
        self.assertIn("deliver ho chuka", r["summary"])
        self.assertIsNone(r["eta_date"])

    def test_unknown_awb_and_missing(self):
        r, _ = run(self.f, "wismo_detail", {"awb": "TZ999999"})
        self.assertEqual(r["error"], "shipment_not_found")
        r, _ = run(self.f, "wismo_detail", {}, awb=None, text="where is it")
        self.assertEqual(r["error"], "awb_required")

    def test_transit_eta_depends_on_cutoff(self):
        early = wismo_detail.eta_window("IN_TRANSIT", NOW)[0]
        late = wismo_detail.eta_window("IN_TRANSIT", NOW.replace(hour=15))[0]
        self.assertEqual((late - early).days, 1)


class AddressTests(unittest.TestCase):
    f = address_update.AddressUpdateFeature()
    NEW = "7 Park Street, Gomti Nagar, Lucknow 226016"

    def test_update_creates_ticket(self):
        r, ctx = run(self.f, "update_delivery_address", {"awb": AWB, "new_address": self.NEW})
        self.assertTrue(r["updated"])
        self.assertEqual(ctx.backend.orders.get(AWB)["address_text"], self.NEW)
        self.assertEqual(ctx.backend.tickets.get(r["ticket_id"])["kind"], "address_change")

    def test_locked_when_out_for_delivery(self):
        r, ctx = run(self.f, "update_delivery_address", {"awb": AWB, "new_address": self.NEW},
                     carrier=FeatureCarrier("OUT_FOR_DELIVERY"))
        self.assertEqual(r["error"], "address_locked")
        self.assertEqual(ctx.backend.orders.address_history(AWB), [])

    def test_pincode_change_goes_to_human(self):
        r, _ = run(self.f, "update_delivery_address", {"awb": AWB, "new_address": "7 Park Street, Delhi 110001"})
        self.assertEqual(r["error"], "pincode_change_needs_human")

    def test_validation_and_change_limit(self):
        r, _ = run(self.f, "update_delivery_address", {"awb": AWB, "new_address": "short"})
        self.assertEqual(r["error"], "address_too_short")
        ctx = make_ctx()
        for i in range(2):
            self.f.run_tool("update_delivery_address", {"awb": AWB, "new_address": "%d Park Street, Lucknow 226016" % (i + 1)}, ctx)
        r = self.f.run_tool("check_address_change", {"awb": AWB}, ctx)
        self.assertEqual(r["error"], "too_many_changes")
        self.assertFalse(r["can_change"])

    def test_ticket_failure_still_reports_update(self):
        be = FakeBackend()
        be.tickets.fail_create = True
        r, _ = run(self.f, "update_delivery_address", {"awb": AWB, "new_address": self.NEW}, backend=be)
        self.assertTrue(r["updated"])
        self.assertIn("ticket_error", r)


class CancelTests(unittest.TestCase):
    f = cancel_order.CancelOrderFeature()

    def test_cancel_in_transit(self):
        r, ctx = run(self.f, "cancel_customer_order", {"awb": AWB, "reason": "ordered twice"})
        self.assertTrue(r["cancelled"])
        self.assertEqual(ctx.backend.orders.get(AWB)["status"], "cancelled")

    def test_blocked_states(self):
        for st, why in (("DELIVERED", "already_delivered"), ("RTO_INITIATED", "already_returning"),
                        ("OUT_FOR_DELIVERY", "too_late_for_cancel"), ("NDR", "too_late_for_cancel")):
            r, ctx = run(self.f, "cancel_customer_order", {"awb": AWB, "reason": "x"}, carrier=FeatureCarrier(st))
            self.assertFalse(r["cancelled"])
            self.assertEqual(r["reason"], why)
            self.assertEqual(ctx.backend.orders.get(AWB)["status"], "active")

    def test_seller_and_category_rules(self):
        be = FakeBackend()
        be.orders.rows[AWB]["seller"] = "FreshBox"
        r, _ = run(self.f, "check_cancellable", {"awb": AWB}, backend=be)
        self.assertEqual(r["reason"], "seller_blocks_cancel")
        be.orders.rows[AWB]["seller"] = "Other"
        be.orders.rows[AWB]["category"] = "grocery"
        r, _ = run(self.f, "check_cancellable", {"awb": AWB}, backend=be, language="hinglish")
        self.assertFalse(r["cancellable"])
        self.assertIn("nahi", r["message"])

    def test_missing_reason(self):
        r, _ = run(self.f, "cancel_customer_order", {"awb": AWB})
        self.assertEqual(r["error"], "bad_arguments")


class CodRefundTests(unittest.TestCase):
    f = cod_refund.CodRefundFeature()

    def car(self, **kw):
        return FeatureCarrier("DELIVERED", **kw)

    def test_payout(self):
        c = self.car()
        r, _ = run(self.f, "cod_refund_payout", {"awb": AWB, "amount_inr": 800, "vpa": "ravi@okaxis"}, carrier=c)
        self.assertTrue(r["paid"])
        self.assertIn(("create_refund", AWB, 800, "refund", "ravi@okaxis"), c.calls)

    def test_old_window_is_five_days(self):
        r, _ = run(self.f, "cod_refund_check", {"awb": AWB, "amount_inr": 800}, carrier=self.car(delivered_days_ago=6))
        self.assertFalse(r["allowed"])
        self.assertEqual(r["reason"], "outside_window")
        self.assertEqual(r["window_days"], 5)

    def test_over_limit_creates_approval_ticket(self):
        c = self.car(amount_inr=3000)
        r, ctx = run(self.f, "cod_refund_payout", {"awb": AWB, "amount_inr": 2500, "vpa": "a.b@upi"}, carrier=c)
        self.assertEqual(r["reason"], "needs_human_approval")
        self.assertNotIn("create_refund", c.names())
        self.assertEqual(ctx.backend.tickets.get(r["ticket_id"])["kind"], "refund_approval")

    def test_guards(self):
        r, _ = run(self.f, "cod_refund_payout", {"awb": AWB, "amount_inr": 100, "vpa": "bad vpa"}, carrier=self.car())
        self.assertEqual(r["error"], "invalid_vpa")
        r, _ = run(self.f, "cod_refund_check", {"awb": AWB, "amount_inr": 100}, carrier=self.car(payment_mode="PREPAID"))
        self.assertEqual(r["reason"], "not_cod")
        r, _ = run(self.f, "cod_refund_check", {"awb": AWB, "amount_inr": 9999}, carrier=self.car())
        self.assertEqual(r["reason"], "amount_exceeds_order")
        r, _ = run(self.f, "cod_refund_check", {"awb": AWB, "amount_inr": "abc"}, carrier=self.car())
        self.assertEqual(r["error"], "bad_arguments")
        r, _ = run(self.f, "cod_refund_check", {"awb": AWB, "amount_inr": 100}, carrier=FeatureCarrier("IN_TRANSIT"))
        self.assertEqual(r["reason"], "not_delivered")


class FeedbackTests(unittest.TestCase):
    f = rider_feedback.RiderFeedbackFeature()

    def test_save_then_append(self):
        ctx = make_ctx()
        r = self.f.run_tool("save_rider_feedback", {"awb": AWB, "rating": 2, "comment": "rider was rude"}, ctx)
        self.assertTrue(r["saved"])
        t = ctx.backend.tickets.get(r["ticket_id"])
        self.assertEqual(t["priority"], "high")
        self.assertIn("rating=2", t["notes"][0]["text"])
        r2 = self.f.run_tool("save_rider_feedback", {"awb": AWB, "rating": 5}, ctx)
        self.assertTrue(r2["appended"])
        self.assertEqual(len(ctx.backend.tickets.list(awb=AWB)), 1)

    def test_bad_rating_and_masking(self):
        for bad in (0, 6, "x", None):
            r, _ = run(self.f, "save_rider_feedback", {"awb": AWB, "rating": bad})
            self.assertEqual(r["error"], "bad_arguments")
        self.assertEqual(rider_feedback.clean_comment("you idiot"), "you *****")


class SlotTests(unittest.TestCase):
    f = slot_picker.SlotPickerFeature()

    def test_before_cutoff_offers_today(self):
        r, _ = run(self.f, "list_delivery_slots", {"awb": AWB}, carrier=FeatureCarrier("NDR"))
        self.assertEqual(r["slots"][0]["slot"], "today")
        self.assertIn("11:00", r["cutoff_note"])

    def test_after_cutoff_hides_today(self):
        late = NOW.replace(hour=12, minute=10)
        r, _ = run(self.f, "list_delivery_slots", {"awb": AWB}, carrier=FeatureCarrier("NDR", now=late), now=late)
        self.assertEqual(r["slots"][0]["slot"], "tomorrow")
        r, ctx = run(self.f, "book_delivery_slot", {"awb": AWB, "slot": "today"}, carrier=FeatureCarrier("NDR", now=late), now=late)
        self.assertEqual(r["error"], "slot_not_available")
        self.assertNotIn("reschedule", ctx.carrier.names())

    def test_book_once_even_on_timeout(self):
        c = FeatureCarrier("NDR")
        c.timeout_next = True
        r, _ = run(self.f, "book_delivery_slot", {"awb": AWB, "slot": "tomorrow"}, carrier=c)
        self.assertEqual(r["error"], "backend_call_failed")
        self.assertEqual(c.names().count("reschedule"), 1)

    def test_tier3_and_blocked(self):
        slots = slot_picker.build_slots(NOW, "tier3")
        self.assertEqual(len(slots[0]["windows"]), 2)
        r, _ = run(self.f, "list_delivery_slots", {"awb": AWB}, carrier=FeatureCarrier("DELIVERED"))
        self.assertEqual(r["error"], "not_reschedulable")

    def test_valid_slot_dates(self):
        d = (NOW + timedelta(days=2)).date().isoformat()
        self.assertTrue(slot_picker.valid_slot(d, NOW))
        self.assertFalse(slot_picker.valid_slot("2026-12-30", NOW))
        self.assertFalse(slot_picker.valid_slot("2026-13-45", NOW))
        self.assertFalse(slot_picker.valid_slot("someday", NOW))


class DelayTests(unittest.TestCase):
    def test_plan_many(self):
        old = NOW - timedelta(hours=40)
        items = [
            {"shipment": {"awb": "TZ1", "status": "IN_TRANSIT", "phone": "+91-90000-00001"}, "last_scan_ts": old.isoformat()},
            {"shipment": {"awb": "TZ2", "status": "NDR", "phone": "+91-90000-00002"}, "language": "hinglish"},
            {"shipment": {"awb": "TZ3", "status": "DELIVERED"}},
            {"shipment": {"awb": "TZ2", "status": "NDR"}},
            {"shipment": {"awb": "TZ4", "status": "OUT_FOR_DELIVERY"}},
        ]
        plans = delay_notifier.plan_messages(items, NOW)
        self.assertEqual([p["awb"] for p in plans], ["TZ2", "TZ1"])
        self.assertIn("nahi ho paaya", plans[0]["text"])
        evening = delay_notifier.plan_messages(items, NOW.replace(hour=19))
        self.assertIn("ofd_late", [p["reason"] for p in evening])
        self.assertTrue(plans[0]["phone_masked"].endswith("0002"))

    def test_slot_passed(self):
        sh = {"awb": "TZ5", "status": "RESCHEDULED"}
        r = delay_notifier.detect_reason(sh, NOW, slot_date=(NOW - timedelta(days=1)).date())
        self.assertEqual(r, "slot_passed")

    def test_tool(self):
        f = delay_notifier.DelayNotifierFeature()
        r, _ = run(f, "plan_delay_message", {"awb": AWB}, carrier=FeatureCarrier("NDR"))
        self.assertTrue(r["delayed"])
        r, _ = run(f, "plan_delay_message", {"awb": AWB}, carrier=FeatureCarrier("DELIVERED"))
        self.assertFalse(r["delayed"])


class PromiseTests(unittest.TestCase):
    f = promise_tracker.PromiseTrackerFeature()

    def test_record_and_duplicate(self):
        ctx = make_ctx()
        r = self.f.run_tool("record_eta_promise", {"awb": AWB, "eta": "tomorrow"}, ctx)
        self.assertTrue(r["recorded"])
        self.assertEqual(r["eta"], "2026-11-03")
        r2 = self.f.run_tool("record_eta_promise", {"awb": AWB, "eta": "2026-11-03"}, ctx)
        self.assertFalse(r2["recorded"])
        self.assertEqual(self.f.run_tool("record_eta_promise", {"awb": AWB, "eta": "soon"}, ctx)["error"], "bad_arguments")

    def test_evaluate_states(self):
        rows = [{"id": 1, "awb": "A", "summary": "ETA 2026-11-02"}, {"id": 2, "awb": "B", "summary": "ETA 2026-11-02"},
                {"id": 3, "awb": "C", "summary": "ETA 2026-11-09"}, {"id": 4, "awb": "D", "summary": "junk"}]
        v = promise_tracker.evaluate(rows, {"A": "2026-11-02", "B": "2026-11-04"}, NOW)
        self.assertEqual({x["awb"]: x["state"] for x in v}, {"A": "kept", "B": "broken", "C": "pending"})
        late = promise_tracker.evaluate(rows, {}, NOW + timedelta(days=10))
        self.assertEqual([x["state"] for x in late], ["broken", "broken", "broken"])

    def test_check_with_delivery(self):
        be = FakeBackend()
        be.tickets.create(AWB, "eta_promise", "ETA 2026-11-01")
        c = FeatureCarrier("DELIVERED", delivered_days_ago=1)  # delivered 2026-11-01
        r, _ = run(self.f, "check_promises", {"awb": AWB}, carrier=c, backend=be)
        self.assertEqual(r["promises"][0]["state"], "kept")
        be2 = FakeBackend()
        be2.tickets.create(AWB, "eta_promise", "ETA 2026-10-30")
        r, _ = run(self.f, "check_promises", {"awb": AWB}, carrier=c, backend=be2)
        self.assertEqual(len(r["broken"]), 1)


class HandoffTests(unittest.TestCase):
    f = handoff.HandoffFeature()

    def test_create_and_idempotent_open(self):
        ctx = make_ctx(text="mujhe human se baat karni hai", language="hinglish")
        self.assertTrue(self.f.can_handle(ctx))
        r = self.f.run_tool("create_handoff", {"awb": AWB, "reason": "customer_asked", "note": "wants call"}, ctx)
        self.assertTrue(r["created"])
        self.assertIn("xxxxxx0001", r["summary"])
        self.assertNotIn("+91-90000", r["summary"])
        r2 = self.f.run_tool("create_handoff", {"awb": AWB, "reason": "other"}, ctx)
        self.assertTrue(r2["already_open"])

    def test_priority(self):
        self.assertEqual(handoff.priority_for("other", 100, "I will go to consumer court"), "urgent")
        self.assertEqual(handoff.priority_for("policy_limit", 100, ""), "high")
        self.assertEqual(handoff.priority_for("other", 5000, ""), "high")
        self.assertEqual(handoff.priority_for("other", 100, "hi"), "normal")

    def test_can_handle_negative_and_missing(self):
        self.assertFalse(self.f.can_handle(make_ctx(text="where is my parcel")))
        r, _ = run(self.f, "create_handoff", {"awb": AWB}, text="x")
        self.assertEqual(r["error"], "bad_arguments")


class NotReceivedTests(unittest.TestCase):
    f = not_received_helper.NotReceivedHelperFeature()

    def test_question_flow_and_intake(self):
        c = FeatureCarrier("DELIVERED")
        ctx = make_ctx(carrier=c)
        r = self.f.run_tool("not_received_next_question", {"awb": AWB}, ctx)
        self.assertEqual(r["ask"], "checked_neighbours")
        answers = {"checked_neighbours": "nahi"}
        r = self.f.run_tool("not_received_next_question", {"awb": AWB, "answers": answers}, ctx)
        self.assertEqual(r["ask"], "address_correct")
        answers.update(address_correct="haan", delivery_time_seen="no")
        r = self.f.run_tool("not_received_next_question", {"awb": AWB, "answers": answers}, ctx)
        self.assertTrue(r["done"])
        self.assertEqual(len(r["observations"]), 2)
        self.assertEqual(ctx.backend.tickets.get(r["ticket_id"])["kind"], "not_received_intake")
        self.assertEqual(c.names().count("open_rider_dispute"), 0)
        self.assertNotIn("create_refund", c.names())

    def test_otp_first_and_not_applicable(self):
        ctx = make_ctx(carrier=FeatureCarrier("DELIVERED", otp_required=True), language="hinglish")
        r = self.f.run_tool("not_received_next_question", {"awb": AWB}, ctx)
        self.assertEqual(r["ask"], "otp_shared")
        self.assertIn("OTP", r["question"])
        r, _ = run(self.f, "not_received_next_question", {"awb": AWB}, carrier=FeatureCarrier("IN_TRANSIT"))
        self.assertFalse(r["applicable"])

    def test_answer_normalisation(self):
        self.assertEqual(not_received_helper.norm_answer("Haan"), "yes")
        self.assertEqual(not_received_helper.norm_answer("pata nahi"), "unclear")


class NoDisputeAnywhereTests(unittest.TestCase):
    def test_no_feature_calls_dispute_or_escalate(self):
        from tezdak.features import FeatureRegistry
        reg = FeatureRegistry.default()
        for st in ("IN_TRANSIT", "NDR", "DELIVERED", "OUT_FOR_DELIVERY", "RESCHEDULED"):
            c = FeatureCarrier(st)
            ctx = make_ctx(carrier=c, text="rider aaya nahi")
            for spec in reg.all_specs():
                args = {"awb": AWB, "reason": "customer_asked", "amount_inr": 100, "vpa": "a@upi", "rating": 3,
                        "slot": "tomorrow", "new_address": "9 Lane, Lucknow 226016", "eta": "tomorrow"}
                reg.dispatch(spec["name"], {k: v for k, v in args.items() if k in spec["parameters"]["properties"]}, ctx)
            self.assertNotIn("open_rider_dispute", c.names())
            self.assertNotIn("escalate", c.names())


if __name__ == "__main__":
    unittest.main()
