import glob
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from tezdak import router  # noqa: E402
from tezdak.nlu import facade  # noqa: E402
from tezdak.nlu.rules_v1 import BASE_INTENTS, classify_base  # noqa: E402

PHRASES = [
    "Where is my parcel?", "Track my order please", "kab aayega mera parcel", "mera parcel kahan hai",
    "any update on TZ1234567", "when will it be delivered", "kitne din lagenge", "status kya hai",
    "Rider aaya hi nahi", "nobody came to deliver", "delivery boy never showed up", "failed delivery attempt but I was home",
    "koi nahi aaya aaj", "call nahi kiya rider ne", "this looks like a fake attempt", "NDR raised wrongly",
    "My order shows delivered but I never got it", "parcel delivered dikha raha hai par nahi mila",
    "marked delivered but haven't received it", "delivery ho gaya bola, nahi mila",
    "please reschedule", "deliver it tomorrow", "kal deliver karo", "another attempt please",
    "try again today", "mujhe slot chahiye", "aaj deliver kar do", "re-attempt karwa do",
    "I want a refund", "cancel my order", "hello", "thanks a lot", "change my address", "great rider, thanks",
    "mera paisa wapas chahiye", "I never received my parcel", "parcel nahi mila", "nahin mila abhi tak",
    "speak to a human", "wrong item delivered", "", "asdfgh", "Rider aaya hi nahi, mera parcel kab milega?",
    "My parcel says delivery failed but I was around. When will it come?",
]


def dev_texts():
    out = []
    root = os.path.join(HERE, "fixtures", "dev6")
    for path in sorted(glob.glob(os.path.join(root, "*.json"))):
        with open(path, encoding="utf-8") as fh:
            script = json.load(fh)["customer"]["script"]
        out.append(script["opening"])
        out.extend(r["reply"] for r in script["rules"])
        out.append(script["fallback"])
    return out


class BaseIntentParityTests(unittest.TestCase):
    def test_enough_phrases(self):
        self.assertGreaterEqual(len(PHRASES), 40)

    def test_phrases_match_router(self):
        for text in PHRASES:
            for status in (None, "DELIVERED", "NDR"):
                expected = router.classify(text, status)
                got = facade.classify(text, status, engine="v1").intent
                if expected in router.INTENTS and expected != "other":
                    self.assertEqual(got, expected, (text, status))
                else:
                    self.assertNotIn(got, BASE_INTENTS[:-1], (text, status))

    def test_dev_scripts_match_router(self):
        texts = dev_texts()
        self.assertGreaterEqual(len(texts), 30)
        for text in texts:
            expected = router.classify(text)
            got = facade.classify(text, engine="v1").intent
            if expected != "other":
                self.assertEqual(got, expected, text)
            else:
                self.assertNotIn(got, BASE_INTENTS[:-1], text)

    def test_base_ladder_equals_router_exactly(self):
        for text in PHRASES + dev_texts():
            for status in (None, "DELIVERED"):
                self.assertEqual(classify_base(text, status), router.classify(text, status), text)

    def test_base_intent_set_matches_router(self):
        self.assertEqual(tuple(BASE_INTENTS), tuple(router.INTENTS))

    def test_extras_only_when_router_other(self):
        for text in PHRASES + dev_texts():
            r = router.classify(text)
            got = facade.classify(text, engine="v1").intent
            if r == "other":
                continue
            self.assertEqual(got, r)

    def test_specific_extras_present(self):
        self.assertEqual(facade.classify("change my address", engine="v1").intent, "address_change")
        self.assertEqual(facade.classify("cancel my order", engine="v1").intent, "cancel_order")
        self.assertEqual(facade.classify("I want a refund", engine="v1").intent, "refund_status")


if __name__ == "__main__":
    unittest.main()
