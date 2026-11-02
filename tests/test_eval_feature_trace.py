import json
import os
import unittest
from pathlib import Path
from unittest import mock

try:
    from carrier_sim import CarrierSim  # noqa: F401
    HAVE_SIM = True
except ImportError:
    HAVE_SIM = False

DEV = Path(__file__).resolve().parent / "fixtures" / "dev6"


class ScriptedLLM:
    """Calls one feature tool, then answers."""
    usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "calls": 0}

    def __init__(self, *a, **kw):
        self.n = 0

    def respond(self, messages, tools=None):
        self.n += 1
        names = [t["name"] for t in (tools or [])]
        if self.n == 1 and "check_address_change" in names:
            return {"output": [{"type": "function_call", "call_id": "c1", "name": "check_address_change",
                                "arguments": json.dumps({"awb": json.loads((DEV / "dev-001.json").read_text())["world"]["shipment"]["awb"]})}]}
        return {"output": [{"type": "message", "content": "Done.\nETA: none"}]}


@unittest.skipUnless(HAVE_SIM, "carrier_sim not importable")
class FeatureTraceTests(unittest.TestCase):
    def test_feature_calls_and_session_start_are_traced(self):
        from eval.run_eval import default_agent_factory, run_scenario
        sc = json.loads((DEV / "dev-001.json").read_text())
        sc["customer"]["script"]["opening"] = "I want to change my delivery address"
        with mock.patch.dict(os.environ, {"TEZDAK_NLU_ENGINE": "v1", "LLM_MODE": "mock"}), \
                mock.patch("tezdak.llm.LLMClient", ScriptedLLM):
            res = run_scenario(sc, default_agent_factory)
        kinds = [e["kind"] for e in res.trace]
        self.assertEqual(kinds[0], "session_start")
        self.assertIn("feature_call", kinds)
        self.assertIn("feature_result", kinds)
        call = next(e for e in res.trace if e["kind"] == "feature_call")
        self.assertEqual(call["data"]["name"], "check_address_change")

    def test_session_start_records_channel(self):
        from eval.run_eval import default_agent_factory, run_scenario
        sc = json.loads((DEV / "dev-002.json").read_text())
        sc["channel"] = "whatsapp"
        with mock.patch.dict(os.environ, {"LLM_MODE": "mock"}):
            res = run_scenario(sc, default_agent_factory)
        self.assertEqual(res.trace[0]["data"]["channel"], "whatsapp")


if __name__ == "__main__":
    unittest.main()
