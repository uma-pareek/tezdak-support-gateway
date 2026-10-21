import unittest
from datetime import datetime

from tezdak.gateway import Gateway, GatewayConfig
from tezdak.gateway.message import IST

PHONE = "919876543210"


def wa(text, mid="w1", kind="text", media_id=None):
    msg = {"from": PHONE, "id": mid, "timestamp": "1790000000", "type": kind}
    if kind == "text":
        msg["text"] = {"body": text}
    else:
        msg[kind] = {"id": media_id, "mime_type": "audio/ogg"}
    return {"entry": [{"changes": [{"value": {"messages": [msg]}}]}]}


class FakeAgent:
    def __init__(self, reply="Your parcel is out for delivery.\nETA: today"):
        self.reply = reply
        self.calls = []

    def __call__(self, conversation):
        self.calls.append(conversation)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Turn:
    def __init__(self, reply):
        self.reply = reply


class GatewayTests(unittest.TestCase):
    def make(self, agent=None, **cfg):
        agent = agent or FakeAgent()
        return Gateway(agent, GatewayConfig(**cfg)), agent

    def test_happy_path_whatsapp(self):
        gw, agent = self.make()
        out = gw.on_message(wa("mera parcel TZ482915 kahan hai"), "whatsapp")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].text, "Your parcel is out for delivery.")
        self.assertEqual(out[0].phone, PHONE)
        self.assertEqual(out[0].in_reply_to, "w1")
        conv = agent.calls[0]
        self.assertEqual(conv["awb"], "TZ482915")
        self.assertEqual(conv["messages"][-1]["role"], "user")

    def test_session_carries_history_and_awb(self):
        gw, agent = self.make()
        gw.on_message(wa("track TZ482915", "w1"), "whatsapp")
        gw.on_message(wa("kab tak aayega", "w2"), "whatsapp")
        conv = agent.calls[1]
        self.assertEqual(conv["awb"], "TZ482915")
        self.assertEqual([m["role"] for m in conv["messages"]], ["user", "assistant", "user"])

    def test_duplicate_message_ignored(self):
        gw, agent = self.make()
        gw.on_message(wa("hi"), "whatsapp")
        self.assertEqual(gw.on_message(wa("hi"), "whatsapp"), [])
        self.assertEqual(len(agent.calls), 1)
        self.assertEqual(gw.stats["duplicates"], 1)

    def test_rate_limit_replies_without_calling_agent(self):
        gw, agent = self.make(rate_capacity=1, rate_refill_per_s=0.0)
        gw.on_message(wa("one", "a"), "whatsapp")
        out = gw.on_message(wa("two", "b"), "whatsapp")
        self.assertEqual(out[0].text, gw.config.rate_limited_reply)
        self.assertEqual(len(agent.calls), 1)

    def test_voice_note_is_transcribed(self):
        gw, agent = self.make()
        gw.on_message(wa("", "v1", kind="audio", media_id="vn-wismo-1"), "whatsapp")
        self.assertIn("TZ482915", agent.calls[0]["messages"][-1]["content"])

    def test_unknown_voice_note_gets_fallback(self):
        gw, agent = self.make()
        out = gw.on_message(wa("", "v2", kind="audio", media_id="unknown"), "whatsapp")
        self.assertEqual(out[0].text, gw.config.voice_failed_reply)
        self.assertEqual(agent.calls, [])

    def test_agent_error_gives_apology(self):
        gw, _ = self.make(agent=FakeAgent(RuntimeError("boom")))
        out = gw.on_message(wa("hi"), "whatsapp")
        self.assertIn("colleague", out[0].text)
        self.assertEqual(gw.stats["agent_errors"], 1)

    def test_long_reply_is_split_and_buttons_on_last(self):
        gw, _ = self.make(agent=FakeAgent("Which slot works for you? " * 80), max_reply_chars=300)
        out = gw.on_message(wa("reschedule"), "whatsapp")
        self.assertGreater(len(out), 1)
        self.assertTrue(all(len(m.text) <= 300 for m in out))
        self.assertEqual(out[0].buttons, [])
        self.assertEqual(out[-1].buttons, ["Today", "Tomorrow", "Day after"])

    def test_agent_result_shapes(self):
        for result in ("plain", {"reply": "plain"}, Turn("plain")):
            gw, _ = self.make(agent=FakeAgent(result))
            self.assertEqual(gw.on_message(wa("hi"), "whatsapp")[0].text, "plain")

    def test_app_channel(self):
        gw, agent = self.make()
        raw = {"user": {"phone": PHONE}, "msg_id": "m1", "text": "where is TZ111222"}
        out = gw.on_message(raw, "app")
        self.assertEqual(out[0].channel, "app")
        self.assertEqual(gw.payload_for(out[0])["user"]["phone"], PHONE)

    def test_payload_uses_template_outside_window(self):
        gw, _ = self.make()
        out = gw.on_message(wa("hi"), "whatsapp")
        later = datetime.fromtimestamp(gw.clock() + 30 * 3600, IST)
        self.assertEqual(gw.payload_for(out[0])["type"], "text")
        self.assertEqual(gw.payload_for(out[0], now=later)["type"], "template")

    def test_proactive_message(self):
        gw, _ = self.make()
        [m] = gw.send_proactive(PHONE, "**Delay** notice", template="delay_v1")
        self.assertEqual((m.text, m.template), ("Delay notice", "delay_v1"))
        with self.assertRaises(ValueError):
            gw.send_proactive("+91 98", "x")

    def test_unknown_channel(self):
        gw, _ = self.make()
        with self.assertRaises(ValueError):
            gw.on_message({}, "telegram")

    def test_events_and_snapshot(self):
        events = []
        gw = Gateway(FakeAgent(), on_event=lambda k, d: events.append(k))
        gw.on_message(wa("hi"), "whatsapp")
        gw.on_message(wa("hi"), "whatsapp")
        self.assertEqual(events, ["duplicate"])
        self.assertEqual(gw.snapshot()["received"], 2)


if __name__ == "__main__":
    unittest.main()
