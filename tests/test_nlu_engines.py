import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tezdak.nlu import facade, flags, intents_v2, rules_v1, shadow  # noqa: E402


class FakeLLM:
    def __init__(self, text=None, exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def respond(self, messages, tools=None):
        self.calls.append(messages)
        if self.exc:
            raise self.exc
        return {"output": [{"type": "message", "content": [{"type": "output_text", "text": self.text}]}]}


class RulesV1Tests(unittest.TestCase):
    CASES = {
        "hi": "greeting", "thank you so much": "thanks", "bye": "goodbye",
        "address galat hai, change karna hai": "address_change", "please cancel": "cancel_order",
        "refund kab milega abhi": "wismo",  # base ladder wins on 'kab'
        "I need my refund": "refund_status", "mujhe talk to manager": "human_agent",
        "the box was damaged": "damaged_item", "wrong size came": "wrong_item",
        "otp not working": "otp_issue", "send invoice": "invoice_request",
        "you are a fraud": "abuse", "payment failed twice": "payment_issue",
        "rider was rude": "rider_behaviour", "hub se pickup karunga": "hold_at_hub",
        "rider ka number do": "contact_rider", "leave it with security guard": "delivery_instructions",
        "i want to return this": "return_request", "delivery charges kitne": "price_query",
        "cod hai kya": "cod_query", "give feedback about service": "feedback",
        "do you deliver to my pincode 560001, serviceable?": "serviceability",
        "empty box mila": "missing_item", "number badal do": "change_phone",
    }

    def test_table_cases(self):
        for text, want in self.CASES.items():
            self.assertEqual(rules_v1.classify_v1(text)[0], want, text)

    def test_other_and_score(self):
        self.assertEqual(rules_v1.classify_v1("blue banana"), ("other", 0.0))
        intent, score = rules_v1.classify_v1("cancel")
        self.assertTrue(0.4 <= score <= 1.0)

    def test_priority_abuse_beats_refund(self):
        self.assertEqual(rules_v1.classify_v1("you fraud give refund")[0], "abuse")

    def test_counts(self):
        self.assertGreaterEqual(rules_v1.rule_count(), 150)
        self.assertGreaterEqual(len(rules_v1.ALL_INTENTS), 25)

    def test_nahi_chahiye_refund_not_cancel(self):
        self.assertEqual(rules_v1.classify_v1("mujhe refund nahi chahiye")[0], "refund_status")


class IntentsV2Tests(unittest.TestCase):
    def test_taxonomy_size(self):
        self.assertEqual(len(intents_v2.INTENTS_V2), 18)
        self.assertEqual(len(set(intents_v2.INTENTS_V2)), 18)

    def test_prompt_lists_every_label(self):
        p = intents_v2.build_system_prompt()
        for label in intents_v2.INTENTS_V2:
            self.assertIn(f"- {label}:", p)

    def test_no_llm_falls_back_to_rules(self):
        r = intents_v2.classify_v2("hello")
        self.assertEqual((r.intent, r.source), ("small_talk", "rules"))
        r = intents_v2.classify_v2("damaged box")
        self.assertEqual(r.intent, "item_problem")

    def test_llm_path(self):
        llm = FakeLLM(json.dumps({"intent": "cancel_order", "confidence": 0.9, "reason": "asks to cancel"}))
        r = intents_v2.classify_v2("ye order nahi chahiye", llm=llm, shipment_status="IN_TRANSIT")
        self.assertEqual((r.intent, r.source, r.confidence), ("cancel_order", "llm", 0.9))
        self.assertIn("IN_TRANSIT", llm.calls[0][1]["content"])

    def test_fenced_and_bare_output(self):
        self.assertEqual(intents_v2.parse_llm_output('```json\n{"intent":"wismo","confidence":0.8}\n```')[0], "wismo")
        self.assertEqual(intents_v2.parse_llm_output("wismo")[0], "wismo")
        self.assertIsNone(intents_v2.parse_llm_output("{'intent': 'nope'}"))
        self.assertIsNone(intents_v2.parse_llm_output(""))

    def test_bad_output_and_errors_fall_back(self):
        r = intents_v2.classify_v2("hello", llm=FakeLLM("gibberish"))
        self.assertEqual((r.intent, r.source), ("small_talk", "llm_rejected"))
        r = intents_v2.classify_v2("hello", llm=FakeLLM(exc=RuntimeError("down")))
        self.assertEqual((r.intent, r.source), ("small_talk", "rules"))
        low = FakeLLM(json.dumps({"intent": "abuse", "confidence": 0.2}))
        self.assertEqual(intents_v2.classify_v2("hello", llm=low).source, "llm_rejected")

    def test_custom_fallback(self):
        r = intents_v2.classify_v2("x", fallback=lambda t, s=None: ("cancel_order", 0.7))
        self.assertEqual(r.intent, "cancel_order")

    def test_with_real_mock_llm(self):
        from tezdak.config import Config
        from tezdak.llm import LLMClient

        r = intents_v2.classify_v2("hello", llm=LLMClient(Config(llm_mode="mock")))
        self.assertIn(r.intent, intents_v2.INTENTS_V2)


class FlagsAndShadowTests(unittest.TestCase):
    def test_flag_default_and_values(self):
        self.assertEqual(flags.engine_name({}), "v1")
        self.assertEqual(flags.engine_name({"TEZDAK_NLU_ENGINE": "V2"}), "v2")
        self.assertEqual(flags.engine_name({"TEZDAK_NLU_ENGINE": "bogus"}), "v1")
        self.assertTrue(flags.is_shadow({"TEZDAK_NLU_ENGINE": "shadow"}))

    def test_shadow_summary(self):
        log = shadow.ShadowLog(max_records=3)
        self.assertEqual(log.summary()["total"], 0)
        shadow.run_shadow("hello", log=log)
        shadow.run_shadow("where is my parcel", log=log)
        shadow.run_shadow("fraud", log=log)
        s = log.summary()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["agreement"], 1.0)
        shadow.run_shadow("x", log=log, llm=FakeLLM(json.dumps({"intent": "abuse", "confidence": 0.9})))
        s = log.summary()
        self.assertEqual(s["total"], 3)  # capped
        self.assertLess(s["agreement"], 1.0)
        self.assertIn("other->abuse", s["disagreements"])

    def test_facade_engines(self):
        r = facade.classify("Rider aaya hi nahi", engine="v1")
        self.assertEqual((r.intent, r.engine, r.language), ("ndr_complaint", "v1", "hinglish"))
        r2 = facade.classify("cancel my order", engine="v2")
        self.assertEqual((r2.intent, r2.engine), ("cancel_order", "v2"))
        shadow.DEFAULT_LOG.clear()
        r3 = facade.classify("hello", engine="shadow")
        self.assertEqual((r3.intent, r3.engine), ("greeting", "shadow"))
        self.assertEqual(shadow.summary()["total"], 1)
        shadow.DEFAULT_LOG.clear()

    def test_facade_env_default(self):
        old = os.environ.pop("TEZDAK_NLU_ENGINE", None)
        try:
            self.assertEqual(facade.classify("hello").engine, "v1")
        finally:
            if old is not None:
                os.environ["TEZDAK_NLU_ENGINE"] = old

    def test_facade_entities_and_dict(self):
        r = facade.classify("TZ1234567 kab aayega, pincode 560001")
        self.assertEqual(r.entities.awb, "TZ1234567")
        self.assertEqual(r.to_dict()["entities"]["pincodes"], ["560001"])


if __name__ == "__main__":
    unittest.main()
