import json
import os
import unittest
from pathlib import Path

try:
    from carrier_sim import CarrierSim  # noqa: F401
    HAVE_SIM = True
except ImportError:
    HAVE_SIM = False

DEV = Path(__file__).resolve().parent / "fixtures" / "dev6"


def scenarios():
    return [json.loads(p.read_text()) for p in sorted(DEV.glob("*.json"))]


@unittest.skipUnless(HAVE_SIM, "carrier_sim not importable")
class WiringTests(unittest.TestCase):
    def setUp(self):
        os.environ["LLM_MODE"] = "mock"
        for k in ("TEZDAK_NLU_ENGINE", "TEZDAK_PROMPT_VERSION", "TEZDAK_FEATURES_DISABLED"):
            os.environ.pop(k, None)

    def test_default_run_unchanged_by_backend(self):
        """Giving the agent a backend must not change what the base agent does on the dev scenarios."""
        from eval.run_eval import _AwbAdapter, default_agent_factory, run_scenario
        from tezdak.agent import SupportAgent
        from tezdak.carrier_client import CarrierClient
        from tezdak.llm import LLMClient

        def without_backend(carrier):
            return _AwbAdapter(SupportAgent(LLMClient(), CarrierClient(carrier)), carrier.awb)

        for sc in scenarios():
            a = run_scenario(sc, without_backend)
            b = run_scenario(sc, default_agent_factory)
            self.assertEqual([e["type"] for e in a.ledger], [e["type"] for e in b.ledger], sc["id"])
            for key in ("bookings", "refunds_paid_inr", "escalated", "closed"):
                self.assertEqual(a.facts[key], b.facts[key], (sc["id"], key))

    def test_planner_present_when_backend_given(self):
        from eval.run_eval import default_agent_factory, run_scenario
        sc = scenarios()[0]
        seen = {}

        def factory(carrier):
            ag = default_agent_factory(carrier)
            seen["planner"] = ag._agent.planner
            return ag
        run_scenario(sc, factory)
        self.assertIsNotNone(seen["planner"])

    def test_nlu_engine_flag_selects_facade(self):
        os.environ["TEZDAK_NLU_ENGINE"] = "v1"
        from tezdak.app import build_app
        sc = scenarios()[0]
        app = build_app(scenario=sc)
        turn = app.agent.handle({"awb": sc["world"]["shipment"]["awb"],
                                 "messages": [{"role": "user", "content": "I want to change my delivery address"}]})
        self.assertEqual(turn.intent, "address_change")

    def test_gateway_to_agent_roundtrip(self):
        from tezdak.app import build_app
        sc = scenarios()[0]
        app = build_app(scenario=sc)
        raw = {"user": {"phone": "+919000000001", "name": "Test"}, "msg_id": "m-1",
               "text": "Where is my parcel %s?" % sc["world"]["shipment"]["awb"]}
        out = app.gateway.on_message(raw, "app")
        self.assertTrue(out)
        self.assertTrue(out[0].text)


if __name__ == "__main__":
    unittest.main()
