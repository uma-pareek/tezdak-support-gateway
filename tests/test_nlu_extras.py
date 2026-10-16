import os
import sys
import unittest
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tezdak.nlu import evaluation, lexicon, slots  # noqa: E402
from tezdak.nlu.rules_v1 import classify_v1  # noqa: E402

NOW = datetime(2026, 3, 10, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))


class LexiconTests(unittest.TestCase):
    def test_expand(self):
        self.assertEqual(lexicon.expand("pls cncl my ord"), "please cancel my order")
        self.assertEqual(lexicon.expand("whr is my parcel"), "where is my parcel")
        self.assertEqual(lexicon.expand(lexicon.expand("plz")), "please")

    def test_yes_no(self):
        self.assertEqual(lexicon.yes_no("haan ji theek hai"), "yes")
        self.assertEqual(lexicon.yes_no("nahi mat karo"), "no")
        self.assertIsNone(lexicon.yes_no("maybe later"))


class SlotTests(unittest.TestCase):
    def test_full_slot(self):
        r = slots.fill_slots("kal shaam 6 baje ke baad deliver karo", NOW)
        self.assertEqual((r.day_word, r.day, r.window), ("tomorrow", date(2026, 3, 11), "evening"))
        self.assertTrue(r.complete)

    def test_today_morning(self):
        r = slots.fill_slots("aaj subah chahiye", NOW)
        self.assertEqual((r.day_word, r.earliest_hour, r.latest_hour), ("today", 9, 12))

    def test_before_clock(self):
        r = slots.fill_slots("tomorrow before 5 pm", NOW)
        self.assertEqual(r.latest_hour, 17)
        self.assertTrue(r.complete)

    def test_incomplete(self):
        r = slots.fill_slots("deliver it", NOW)
        self.assertFalse(r.complete)
        self.assertEqual(slots.describe(r), "no slot given")
        self.assertIn("tomorrow", slots.describe(slots.fill_slots("kal subah", NOW)))


class EvaluationTests(unittest.TestCase):
    DATA = [("hello", "greeting"), ("cancel it", "cancel_order"), ("cancel it", "refund_status"), ("zzz", "other")]

    def test_evaluate(self):
        res = evaluation.evaluate(lambda t: classify_v1(t)[0], self.DATA)
        self.assertEqual(res["total"], 4)
        self.assertEqual(res["accuracy"], 0.75)
        self.assertEqual(res["per_intent"]["cancel_order"]["recall"], 1.0)
        self.assertEqual(res["confusion"], {"refund_status->cancel_order": 1})
        self.assertIn("miss", evaluation.report(res))

    def test_compare_and_group(self):
        diffs = evaluation.compare(lambda t: "a", lambda t: "a" if t != "x" else "b", ["x", "y"])
        self.assertEqual(diffs, {"x": ("a", "b")})
        self.assertEqual(evaluation.group_by_intent(["a", "b"], lambda t: "k"), {"k": ["a", "b"]})


if __name__ == "__main__":
    unittest.main()
