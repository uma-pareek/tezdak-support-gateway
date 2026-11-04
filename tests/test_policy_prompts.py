import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tezdak.prompts import loader  # noqa: E402

FIELDS = dict(awb="TZ4829301", today="2026-11-02", intent="wismo", language="english", limit=3,
              escalated=False, hint="Check the shipment.", policy="POLICY BLOCK")


class PromptLoader(unittest.TestCase):
    def setUp(self):
        self._old = os.environ.pop("TEZDAK_PROMPT_VERSION", None)

    def tearDown(self):
        os.environ.pop("TEZDAK_PROMPT_VERSION", None)
        if self._old is not None:
            os.environ["TEZDAK_PROMPT_VERSION"] = self._old

    def test_default_v4(self):
        self.assertEqual(loader.get_prompt_version(), "v4")
        self.assertIs(loader.get_system_prompt(), loader.SYSTEM_PROMPTS["v4"])

    def test_env_and_unknown(self):
        os.environ["TEZDAK_PROMPT_VERSION"] = "v6"
        self.assertEqual(loader.get_prompt_version(), "v6")
        with self.assertRaises(ValueError):
            loader.get_system_prompt("v0")

    def test_six_versions(self):
        self.assertEqual(loader.list_versions(), ["v1", "v2", "v3", "v4", "v5", "v6"])

    def test_every_version_renders_and_ends_with_eta_rule(self):
        for v in loader.list_versions():
            text = loader.render_system_prompt(version=v, **FIELDS)
            self.assertIn("TZ4829301", text)
            self.assertIn("ETA:", text)
            self.assertNotIn("{awb}", text)

    def test_policy_slot_only_in_v4(self):
        with_slot = [v for v in loader.list_versions() if "{policy}" in loader.SYSTEM_PROMPTS[v]]
        self.assertEqual(with_slot, ["v4"])

    def test_hinglish_style_appended(self):
        f = dict(FIELDS, language="hinglish")
        self.assertIn("Hinglish notes", loader.render_system_prompt(version="v4", **f))
        self.assertNotIn("Hinglish notes", loader.render_system_prompt(version="v1", **f))
        self.assertNotIn("Hinglish notes", loader.render_system_prompt(version="v4", **FIELDS))

    def test_hints_cover_base_intents(self):
        for v in loader.list_versions():
            hints = loader.get_hints(v)
            for intent in ("wismo", "not_received_after_delivered", "reschedule_request", "ndr_complaint", "other"):
                self.assertIn(intent, hints)

    def test_refusal_and_escalation_text(self):
        self.assertIn("5 days", loader.get_refusal("refund_outside_window", "v1"))
        self.assertIn("Maaf", loader.get_refusal("refund_outside_window", "v4", "hinglish"))
        self.assertIn("colleague", loader.get_escalation("default", "v1"))
        self.assertIn("Maine", loader.get_escalation("ndr", "v4", "hinglish"))
        self.assertEqual(loader.get_escalation("unknown_reason", "v2"), loader.ESCALATIONS["v2"]["default"])

    def test_versions_differ_but_stay_similar(self):
        texts = [loader.SYSTEM_PROMPTS[v] for v in loader.list_versions()]
        self.assertEqual(len(set(texts)), 6)
        for t in texts:
            self.assertTrue(re.search(r"AWB: \{awb\}", t))


if __name__ == "__main__":
    unittest.main()
