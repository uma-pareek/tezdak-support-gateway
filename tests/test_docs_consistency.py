import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DOCS = ROOT / "docs"
TOP = [ROOT / "ARCHITECTURE.md", ROOT / "CHANGELOG.md"]
EXPECTED_DOCS = [
    "README.md", "product-spec.md", "policy-refunds-faq.md", "policy-table-v2.md", "policy-memo-2026-09.md",
    "runbook-oncall.md", "runbook-carrier.md", "slo.md", "dashboard-definitions.md", "prompt-style-guide.md",
    "onboarding.md", "eval-howto.md", "glossary.md",
]
_FRAGMENTS = [("con", "flict"), ("dis", "agree"), ("in", "consisten"), ("tr", "ap"), ("plan", "ted"),
              ("hidden", " set"), ("known", " issue"), ("g", "aps"), ("g", "ap matrix"), ("idem", "poten"),
              ("duplicate", " booking"), ("scor", "er's private"), ("wrong", " label"), ("bia", "sed")]
BANNED = ["".join(f) for f in _FRAGMENTS]


def all_docs():
    return TOP + sorted(DOCS.rglob("*.md"))


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


class DocFilesTests(unittest.TestCase):
    def test_every_doc_exists_and_is_not_empty(self):
        for name in EXPECTED_DOCS:
            p = DOCS / name
            self.assertTrue(p.is_file(), name)
            self.assertGreater(len(p.read_text(encoding="utf-8").strip()), 100, name)
        self.assertEqual(len(list((DOCS / "adr").glob("*.md"))), 6)
        self.assertEqual(len(list((DOCS / "notes").glob("*.md"))), 8)
        for p in TOP:
            self.assertGreater(len(p.read_text(encoding="utf-8").strip()), 100, p.name)

    def test_relative_links_resolve(self):
        link = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
        for p in all_docs():
            for target in link.findall(p.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                path = target.split("#")[0]
                self.assertTrue((p.parent / path).exists(), "%s -> %s" % (p.name, target))

    def test_banned_words_absent(self):
        for p in all_docs():
            text = p.read_text(encoding="utf-8").lower()
            for word in BANNED:
                self.assertNotIn(word, text, "%s contains %r" % (p.name, word))

    def test_changelog_has_releases_0_1_to_0_9(self):
        text = read("CHANGELOG.md")
        for i in range(1, 10):
            self.assertIn("## 0.%d " % i, text)


class PolicyDocTests(unittest.TestCase):
    def test_faq_numbers(self):
        t = read("docs/policy-refunds-faq.md")
        self.assertIn("within 5 days", t)
        self.assertIn("Rs 2000", t)

    def test_table_v2_numbers(self):
        t = read("docs/policy-table-v2.md")
        self.assertIn("| Refund window | 7 days from delivery |", t)
        self.assertIn("Rs 5000", t)
        for cat in ("electronics", "apparel", "grocery", "books"):
            self.assertIn("| %s |" % cat, t)

    def test_memo_numbers(self):
        t = read("docs/policy-memo-2026-09.md")
        self.assertIn("10 days from delivery for prepaid", t)
        self.assertIn("7 days from delivery for COD", t)
        self.assertIn("above Rs 3000", t)
        for row in ("| electronics | 3000 |", "| apparel | 1500 |", "| grocery | 800 |", "| other | 2000 |"):
            self.assertIn(row, t)
        self.assertIn("Rs 100 per customer per rolling 30 days", t)
        self.assertIn("From attempt 3", t)


class CodeNumberTests(unittest.TestCase):
    def test_policy_docs_match_policy_code(self):
        from tezdak.policies import LEGACY_POLICY, POLICY_V2
        from tezdak.policy import v2_table, v3_memo
        self.assertEqual(LEGACY_POLICY["refund_window_days"], 5)
        self.assertEqual(LEGACY_POLICY["human_approval_limit_inr"], 2000)
        self.assertEqual(POLICY_V2["refund_window_days"], 7)
        self.assertEqual(POLICY_V2["human_approval_limit_inr"], 5000)
        self.assertEqual(v2_table.DEFAULTS, {"window_days": 7, "limit_inr": 5000})
        self.assertEqual(v3_memo.WINDOW_PREPAID_DAYS, 10)
        self.assertEqual(v3_memo.WINDOW_COD_DAYS, 7)
        self.assertEqual(v3_memo.CATEGORY_LIMITS_INR, {"electronics": 3000, "apparel": 1500, "grocery": 800})
        self.assertEqual(v3_memo.OTHER_LIMIT_INR, 2000)
        self.assertEqual(v3_memo.GOODWILL_ROLLING_CAP_INR, 100)
        self.assertEqual(v3_memo.GOODWILL_ROLLING_DAYS, 30)
        self.assertEqual(v3_memo.HUB_OVERRIDE_ATTEMPT, 3)

    def test_shared_numbers_match_code(self):
        from tezdak.carrier_client import CARRIER_TIMEOUT_S
        from tezdak.config import Config
        from tezdak.features.slot_picker import CUTOFF_HOUR
        from tezdak.gateway.config import GatewayConfig
        from tezdak.policies import LEGACY_POLICY
        self.assertEqual(CUTOFF_HOUR, 11)
        self.assertEqual(LEGACY_POLICY["max_attempts"], 3)
        self.assertEqual(CARRIER_TIMEOUT_S, 8.0)
        self.assertEqual(Config().max_model_calls, 6)
        gw = GatewayConfig()
        self.assertEqual((gw.session_window, gw.max_reply_chars, gw.dedupe_ttl_s // 60), (12, 900, 15))

        carrier = read("docs/runbook-carrier.md")
        self.assertIn("fee Rs 6", carrier)
        self.assertIn("close at 11:00", carrier)
        self.assertIn("3 attempts", carrier)
        spec = read("docs/product-spec.md")
        self.assertIn("11:00 IST", spec)
        self.assertIn("at most 3 delivery attempts", spec)
        self.assertIn("Rs 6", spec)
        self.assertIn("timeout in seconds. Our client default is 8", carrier)
        self.assertIn("at most 6", read("ARCHITECTURE.md"))

    def test_llm_rates_in_howto_match_code(self):
        from eval.report import RATE_CACHED, RATE_INPUT, RATE_OUTPUT
        text = read("docs/eval-howto.md")
        self.assertIn("%.2f uncached input, %.2f cached input, %.2f output" % (RATE_INPUT, RATE_CACHED, RATE_OUTPUT), text)

    def test_trace_kinds_in_howto_match_code(self):
        from eval.trace import KINDS
        text = read("docs/eval-howto.md")
        for kind in KINDS:
            self.assertIn("`%s`" % kind, text)

    def test_sla_hours_match_code(self):
        from tezdak.backend.settings import DEFAULTS
        from tezdak.backend.sla import PRIORITY_FACTOR
        base = DEFAULTS["ticket_sla_hours"]
        text = read("docs/slo.md")
        for prio, label in (("urgent", "urgent"), ("high", "high"), ("low", "low")):
            self.assertIn("%s %d" % (label, base * PRIORITY_FACTOR[prio]), text)


if __name__ == "__main__":
    unittest.main()
