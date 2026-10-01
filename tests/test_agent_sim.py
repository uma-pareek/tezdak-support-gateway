import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent_fakes  # noqa: E402,F401  (puts the candidate root on sys.path)

try:
    import carrier_sim  # noqa: F401
    HAVE_SIM = True
except ImportError:
    HAVE_SIM = False

from tezdak.agent import SupportAgent  # noqa: E402
from tezdak.carrier_client import CarrierClient  # noqa: E402
from tezdak.config import Config  # noqa: E402
from tezdak.llm import LLMClient  # noqa: E402

SCENARIO = {
    "id": "agent-sim-1",
    "world": {
        "now": "2026-11-02T09:30:00+05:30",
        "latency_profile": "normal",
        "prior_goodwill_30d": False,
        "shipment": {"awb": "TZ4829301", "status": "NDR", "attempts_used": 1, "payment_mode": "PREPAID",
                     "amount_inr": 1499, "pincode": "226016", "tier": "tier2", "phone": "+91-90000-00001",
                     "otp_required": False, "address_geo": {"lat": 26.85, "lng": 80.95}, "vpa": None},
        "scans": agent_fakes.raw_scans(),
    },
}


@unittest.skipUnless(HAVE_SIM, "carrier_sim is not importable (set PYTHONPATH to the private folder)")
class SimConversationTests(unittest.TestCase):
    def test_reschedule_conversation_on_real_sim(self):
        carrier = CarrierClient.from_scenario(SCENARIO)
        agent = SupportAgent(LLMClient(Config(llm_mode="mock")), carrier)
        turn = agent.handle({"awb": "TZ4829301",
                             "messages": [{"role": "user", "content": "please reschedule for tomorrow"}]})
        types = [e["type"] for e in carrier.ledger()]
        self.assertIn("reschedule_applied", types)
        self.assertTrue(turn.reply)
        self.assertEqual(turn.commitments[0]["type"], "eta")


if __name__ == "__main__":
    unittest.main()
