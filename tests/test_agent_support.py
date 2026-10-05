import json
import os
import sys
import unittest
import urllib.request
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import agent_fakes  # noqa: E402
from agent_fakes import FakeCarrier  # noqa: E402

from tezdak import router  # noqa: E402
from tezdak.agent import SupportAgent, eta_commitments  # noqa: E402
from tezdak.config import Config  # noqa: E402
from tezdak.llm import LLMClient, function_calls  # noqa: E402
from tezdak.metrics import Metrics  # noqa: E402
from tezdak.policies import Policies  # noqa: E402
from tezdak.tools import ToolBox  # noqa: E402


def mock_llm():
    return LLMClient(Config(llm_mode="mock"))


def chat(carrier, text, agent=None):
    agent = agent or SupportAgent(mock_llm(), carrier, Policies())
    return agent, agent.handle({"awb": "TZ4829301", "messages": [{"role": "user", "content": text}]})


class RouterTests(unittest.TestCase):
    def test_intents(self):
        cases = {
            "Where is my parcel?": "wismo",
            "mera parcel kahan hai": "wismo",
            "Rider aaya hi nahi, mera parcel kab milega?": "ndr_complaint",
            "nobody came to deliver": "ndr_complaint",
            "Please reschedule for tomorrow": "reschedule_request",
            "kal deliver karo": "reschedule_request",
            "It says delivered but I have not received it": "not_received_after_delivered",
            "parcel nahi mila, delivered dikha raha hai": "not_received_after_delivered",
            "thanks": "other",
        }
        for text, intent in cases.items():
            self.assertEqual(router.classify(text), intent, text)

    def test_status_hint_routes_delivered(self):
        self.assertEqual(router.classify("mujhe parcel nahi mila", "DELIVERED"), "not_received_after_delivered")


class LLMTests(unittest.TestCase):
    def test_mock_never_uses_network(self):
        with mock.patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")):
            _, turn = chat(FakeCarrier(), "Where is my parcel?")
        self.assertIn("out for delivery", turn.reply)

    def test_mock_returns_tool_call_shape(self):
        llm = mock_llm()
        system = "AWB: TZ1\nIntent: wismo\nReply language: english\nToday: 2026-11-02"
        resp = llm.respond([{"role": "system", "content": system}, {"role": "user", "content": "status?"}], tools=[])
        call = function_calls(resp)[0]
        self.assertEqual(call["name"], "get_shipment")
        self.assertEqual(json.loads(call["arguments"]), {"awb": "TZ1"})
        self.assertIn("call_id", call)
        self.assertEqual(llm.usage["calls"], 1)

    def test_default_config_is_mock_without_token(self):
        self.assertEqual(Config.from_env({}).llm_mode, "mock")
        self.assertEqual(Config.from_env({"OPENAI_BASE_URL": "http://x", "OPENAI_API_KEY": "t"}).llm_mode, "live")
        self.assertEqual(Config.from_env({"OPENAI_API_KEY": "t", "LLM_MODE": "mock"}).llm_mode, "mock")

    def test_spend_usd(self):
        llm = mock_llm()
        llm._record({"input_tokens": 1_000_000, "input_tokens_details": {"cached_tokens": 400_000},
                     "output_tokens": 200_000})
        self.assertAlmostEqual(llm.spend_usd(), 0.6 * 0.25 + 0.4 * 0.01 + 0.2 * 0.50, places=6)

    def test_live_url(self):
        cfg = Config(llm_base_url="https://example.test/v1/", llm_token="t", llm_mode="live")
        self.assertEqual(cfg.llm_url, "https://example.test/v1/responses")


class ToolTests(unittest.TestCase):
    def test_get_scans_output_shape(self):
        out = ToolBox(FakeCarrier()).call("get_scans", {"awb": "TZ4829301"})
        self.assertEqual(len(out), 2)
        for row in out:
            self.assertEqual(set(row), {"ts", "status_text", "attempt_n"})

    def test_read_succeeds_after_timeouts(self):
        carrier = FakeCarrier(timeouts_on_reads=2)
        events = []
        box = ToolBox(carrier, on_event=lambda k, d: events.append((k, d.get("attempt"))))
        out = box.call("get_shipment", {"awb": "TZ4829301"})
        self.assertEqual(out["status"], "OUT_FOR_DELIVERY")
        self.assertEqual(carrier.names().count("get_shipment"), 3)
        self.assertEqual([e for e in events if e[0] == "tool_timeout"], [("tool_timeout", 0), ("tool_timeout", 1)])

    def test_read_gives_error_after_budget(self):
        carrier = FakeCarrier(timeouts_on_reads=10)
        out = ToolBox(carrier).call("get_shipment", {"awb": "TZ4829301"})
        self.assertEqual(out["error"], "carrier_timeout")
        self.assertEqual(carrier.names().count("get_shipment"), 3)

    def test_bad_arguments_and_unknown_tool(self):
        box = ToolBox(FakeCarrier())
        self.assertEqual(box.call("reschedule", {"awb": "x"})["error"], "bad_arguments")
        self.assertEqual(box.call("nope", {})["error"], "unknown_tool")

    def test_refund_over_limit_needs_approval(self):
        carrier = FakeCarrier()
        out = ToolBox(carrier).call("create_refund", {"awb": "TZ4829301", "amount_inr": 2500, "kind": "refund"})
        self.assertEqual(out["error"], "needs_human_approval")
        self.assertNotIn("create_refund", carrier.names())


class PolicyTests(unittest.TestCase):
    def test_values(self):
        p = Policies()
        self.assertEqual(p.refund_window_days(), 7)
        self.assertEqual(p.approval_limit_inr(), 2000)
        self.assertEqual(p.legacy["refund_window_days"], 5)
        self.assertEqual(p.v2["human_approval_limit_inr"], 5000)
        self.assertIn("10 days", p.prompt_text())
        self.assertIn("Rs 3000", p.prompt_text())


class AgentTests(unittest.TestCase):
    def test_wismo_out_for_delivery(self):
        carrier = FakeCarrier("OUT_FOR_DELIVERY")
        _, turn = chat(carrier, "Where is my parcel?")
        self.assertEqual(turn.intent, "wismo")
        self.assertEqual(turn.commitments, [{"type": "eta", "value": "today"}])
        self.assertNotIn("ETA:", turn.reply)
        self.assertNotIn("escalate", carrier.names())
        self.assertTrue(turn.closed)

    def test_hinglish_reply(self):
        _, turn = chat(FakeCarrier(), "mera parcel kahan hai")
        self.assertIn("Aapka parcel", turn.reply)

    def test_reschedule_tomorrow(self):
        carrier = FakeCarrier("NDR")
        _, turn = chat(carrier, "Please reschedule it for tomorrow")
        self.assertEqual(carrier.names().count("reschedule"), 1)
        self.assertEqual(turn.commitments, [{"type": "eta", "value": "tomorrow"}])

    def test_reschedule_at_attempt_limit_escalates(self):
        carrier = FakeCarrier("NDR", attempts_used=3)
        _, turn = chat(carrier, "reschedule please")
        self.assertNotIn("reschedule", carrier.names())
        self.assertIn(("escalate", {"awb": "TZ4829301", "kind": "hub_override"}), carrier.log)
        self.assertTrue(turn.escalated)

    def test_ndr_complaint_escalates(self):
        carrier = FakeCarrier("NDR")
        _, turn = chat(carrier, "Rider aaya hi nahi, mera parcel kab milega?")
        self.assertEqual(turn.intent, "ndr_complaint")
        self.assertTrue(turn.escalated)
        for name in ("reschedule", "open_rider_dispute", "create_refund"):
            self.assertNotIn(name, carrier.names())
        self.assertEqual(turn.commitments, [])

    def test_second_complaint_does_not_escalate_again(self):
        carrier = FakeCarrier("NDR")
        agent, _ = chat(carrier, "rider aaya hi nahi")
        _, turn = chat(carrier, "rider aaya hi nahi, kuch karo", agent)
        self.assertEqual(carrier.names().count("escalate"), 1)
        self.assertFalse(turn.escalated)

    def test_delivered_not_received_escalates(self):
        carrier = FakeCarrier("DELIVERED")
        _, turn = chat(carrier, "It shows delivered but I never got it")
        self.assertEqual(turn.intent, "not_received_after_delivered")
        self.assertTrue(turn.escalated)
        self.assertNotIn("create_refund", carrier.names())

    def test_plain_not_received_on_delivered_parcel_escalates(self):
        carrier = FakeCarrier("DELIVERED")
        _, turn = chat(carrier, "mujhe parcel nahi mila")
        self.assertTrue(turn.escalated)

    def test_model_call_budget(self):
        class Looping:
            calls = 0

            def respond(self, messages, tools=None):
                Looping.calls += 1
                return {"output": [{"type": "function_call", "call_id": "c%d" % Looping.calls,
                                    "name": "get_shipment", "arguments": '{"awb": "TZ4829301"}'}]}

        agent = SupportAgent(Looping(), FakeCarrier(), Policies())
        turn = agent.handle({"awb": "TZ4829301", "messages": [{"role": "user", "content": "status"}]})
        self.assertEqual(Looping.calls, 6)
        self.assertEqual(turn.model_calls, 6)
        self.assertTrue(turn.reply)

    def test_awb_taken_from_message(self):
        carrier = FakeCarrier()
        agent = SupportAgent(mock_llm(), carrier, Policies())
        agent.handle([{"role": "user", "content": "where is TZ4829301 ?"}])
        self.assertEqual(carrier.log[0], ("get_shipment", {"awb": "TZ4829301"}))

    def test_eta_parsing(self):
        today = FakeCarrier().now
        self.assertEqual(eta_commitments("ok\nETA: 2026-11-02", today)[1], [{"type": "eta", "value": "today"}])
        self.assertEqual(eta_commitments("ok\nETA: 2026-11-03", today)[1], [{"type": "eta", "value": "tomorrow"}])
        self.assertEqual(eta_commitments("ok\nETA: 2026-11-09", today)[1], [{"type": "eta", "value": "2026-11-09"}])
        self.assertEqual(eta_commitments("ok\nETA: none", today), ("ok", []))
        self.assertEqual(eta_commitments("ok", today), ("ok", []))

    def test_usage_recorded_by_agent_run(self):
        agent, _ = chat(FakeCarrier(), "Where is my parcel?")
        self.assertGreaterEqual(agent.llm.usage["calls"], 2)
        self.assertGreater(agent.llm.spend_usd(), 0)


class MetricsTests(unittest.TestCase):
    def test_resolved_rate(self):
        m = Metrics()
        carrier = FakeCarrier("OUT_FOR_DELIVERY")
        agent = SupportAgent(mock_llm(), carrier, Policies(), metrics=m)
        agent.handle({"awb": "TZ4829301", "messages": [{"role": "user", "content": "where is my parcel"}]})
        carrier2 = FakeCarrier("NDR")
        agent2 = SupportAgent(mock_llm(), carrier2, Policies(), metrics=m)
        agent2.handle({"awb": "TZ4829301", "messages": [{"role": "user", "content": "rider aaya hi nahi"}]})
        self.assertEqual(m.conversations, 2)
        self.assertAlmostEqual(m.resolved_rate, 0.5)
        self.assertIn("resolved_rate: 50.0%", m.report())


if __name__ == "__main__":
    unittest.main()
