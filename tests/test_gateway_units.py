import hashlib
import hmac
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from tezdak.gateway import app_chat, formatting, voicenote, whatsapp
from tezdak.gateway.config import GatewayConfig, GatewayConfigError
from tezdak.gateway.dedupe import Deduper
from tezdak.gateway.message import IST, InboundMessage, OutboundMessage, mask_phone, normalize_phone
from tezdak.gateway.ratelimit import RateLimiter, TokenBucket
from tezdak.gateway.sessions import SessionStore, open_store


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def wa_payload(msgs, contacts=None, statuses=None):
    value = {"messages": msgs, "contacts": contacts or []}
    if statuses:
        value["statuses"] = statuses
    return {"object": "whatsapp_business_account", "entry": [{"id": "1", "changes": [{"field": "messages", "value": value}]}]}


class MessageTests(unittest.TestCase):
    def test_phone_normalisation(self):
        self.assertEqual(normalize_phone("98765 43210"), "919876543210")
        self.assertEqual(normalize_phone("+91-98765-43210"), "919876543210")
        self.assertEqual(normalize_phone("09876543210"), "919876543210")
        self.assertEqual(normalize_phone("123"), "")

    def test_bad_channel_rejected(self):
        with self.assertRaises(ValueError):
            InboundMessage(channel="sms", phone="919876543210")

    def test_naive_ts_becomes_ist_and_id_generated(self):
        m = InboundMessage(channel="app", phone="919876543210", ts=datetime(2026, 1, 1, 10, 0))
        self.assertEqual(m.ts.utcoffset(), timedelta(hours=5, minutes=30))
        self.assertTrue(m.message_id.startswith("gen-"))

    def test_mask_phone(self):
        self.assertEqual(mask_phone("919876543210"), "91********10")


class WhatsAppTests(unittest.TestCase):
    def test_parse_text_with_contact_name(self):
        p = wa_payload(
            [{"from": "919876543210", "id": "wamid.1", "timestamp": "1790000000", "type": "text", "text": {"body": " mera parcel kahan hai "}}],
            contacts=[{"wa_id": "919876543210", "profile": {"name": "Ravi"}}],
        )
        [m] = whatsapp.parse_webhook(p)
        self.assertEqual((m.text, m.sender_name, m.message_id, m.channel), ("mera parcel kahan hai", "Ravi", "wamid.1", "whatsapp"))
        self.assertIsNotNone(m.ts.tzinfo)

    def test_parse_audio_and_button(self):
        p = wa_payload([
            {"from": "919876543210", "id": "a", "type": "audio", "audio": {"id": "vn-wismo-1", "mime_type": "audio/ogg"}},
            {"from": "919876543210", "id": "b", "type": "interactive", "interactive": {"button_reply": {"id": "btn_0", "title": "Kal"}}},
            {"from": "919876543210", "id": "c", "type": "location", "location": {}},
        ])
        msgs = whatsapp.parse_webhook(p)
        self.assertEqual(len(msgs), 2)
        self.assertTrue(msgs[0].has_audio)
        self.assertEqual(msgs[1].text, "Kal")

    def test_status_only_payload_yields_nothing(self):
        p = wa_payload([], statuses=[{"id": "x", "status": "read", "recipient_id": "919876543210"}])
        self.assertEqual(whatsapp.parse_webhook(p), [])
        [st] = whatsapp.parse_statuses(p)
        self.assertEqual(st["status"], "read")

    def test_not_a_webhook(self):
        with self.assertRaises(whatsapp.WebhookError):
            whatsapp.parse_webhook({"hello": 1})

    def test_window_rules(self):
        now = datetime(2026, 11, 9, 12, 0, tzinfo=IST)
        self.assertTrue(whatsapp.window_open(now - timedelta(hours=23), now))
        self.assertFalse(whatsapp.window_open(now - timedelta(hours=25), now))
        self.assertFalse(whatsapp.window_open(None, now))

    def test_payload_choice(self):
        now = datetime(2026, 11, 9, 12, 0, tzinfo=IST)
        msg = OutboundMessage(channel="whatsapp", phone="919876543210", text="Your parcel is on the way")
        inside = whatsapp.build_payload(msg, now - timedelta(hours=1), now)
        outside = whatsapp.build_payload(msg, now - timedelta(hours=30), now)
        self.assertEqual(inside["type"], "text")
        self.assertEqual(outside["type"], "template")
        self.assertEqual(outside["template"]["name"], whatsapp.DEFAULT_TEMPLATE)
        msg.buttons = ["Today", "Tomorrow", "Day after", "extra"]
        buttons = whatsapp.build_payload(msg, now, now)
        self.assertEqual(len(buttons["interactive"]["action"]["buttons"]), 3)

    def test_best_status_and_signature(self):
        self.assertEqual(whatsapp.best_status(["sent", "read", "delivered"]), "read")
        self.assertEqual(whatsapp.best_status(["failed"]), "failed")
        body = b'{"a":1}'
        sig = "sha256=" + hmac.new(b"s3", body, hashlib.sha256).hexdigest()
        self.assertTrue(whatsapp.verify_signature(body, sig, "s3"))
        self.assertFalse(whatsapp.verify_signature(body, sig, "other"))
        self.assertFalse(whatsapp.verify_signature(body, "", "s3"))

    def test_challenge(self):
        params = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "42"}
        self.assertEqual(whatsapp.verify_challenge(params, "tok"), "42")
        with self.assertRaises(whatsapp.WebhookError):
            whatsapp.verify_challenge(params, "bad")


class AppChatTests(unittest.TestCase):
    def test_parse_and_build(self):
        m = app_chat.parse_app_payload({
            "user": {"phone": "9876543210", "name": "Asha"}, "msg_id": "m1", "text": "hi TZ123456",
            "sent_at": "2026-11-09T10:00:00+05:30", "attachments": [{"id": "img1", "kind": "image"}],
        })
        self.assertEqual((m.phone, m.channel, m.message_id), ("919876543210", "app", "m1"))
        self.assertEqual(m.media[0]["id"], "img1")
        out = OutboundMessage(channel="app", phone=m.phone, text="ok", buttons=["Yes"], in_reply_to="m1")
        built = app_chat.build_app_payload(out)
        self.assertEqual(built["quick_replies"], [{"label": "Yes", "value": "Yes"}])
        self.assertEqual(built["reply_to"], "m1")

    def test_missing_phone(self):
        with self.assertRaises(app_chat.AppChatError):
            app_chat.parse_app_payload({"user": {}, "text": "x"})

    def test_typing_event(self):
        self.assertEqual(app_chat.typing_event("91", False)["state"], "stop")


class SessionTests(unittest.TestCase):
    def test_window_awb_and_ttl(self):
        clock = Clock()
        store = SessionStore(ttl_s=100, window=3, clock=clock)
        for i in range(5):
            store.add_message("91x", "user", "msg %d" % i, inbound=True)
        store.add_message("91x", "user", "track TZ482915", inbound=True)
        sess = store.get("91x")
        self.assertEqual(len(sess.messages), 3)
        self.assertEqual(sess.awb, "TZ482915")
        self.assertEqual(sess.to_conversation()["awb"], "TZ482915")
        clock.t += 101
        self.assertIsNone(store.get("91x"))

    def test_json_backend_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            a = open_store(path)
            a.add_message("91y", "user", "hello", inbound=True)
            b = SessionStore(path=path)
            self.assertEqual(b.get("91y").messages[0]["content"], "hello")
            with open(path, "w") as fh:
                fh.write("{not json")
            self.assertEqual(len(SessionStore(path=path)), 0)

    def test_purge(self):
        clock = Clock()
        store = SessionStore(ttl_s=10, clock=clock)
        store.add_message("a", "user", "x")
        clock.t += 11
        self.assertEqual(store.purge_expired(), 1)


class DedupeTests(unittest.TestCase):
    def test_duplicate_lru_and_ttl(self):
        clock = Clock()
        d = Deduper(capacity=2, ttl_s=10, clock=clock)
        self.assertFalse(d.seen("a"))
        self.assertTrue(d.seen("a"))
        d.seen("b")
        d.seen("c")           # evicts a
        self.assertFalse(d.seen("a"))
        clock.t += 11
        self.assertFalse(d.seen("c"))   # expired
        self.assertFalse(d.seen(""))    # empty id never dedupes


class RateLimitTests(unittest.TestCase):
    def test_bucket_refills(self):
        clock = Clock()
        b = TokenBucket(2, 1.0, clock)
        self.assertTrue(b.take() and b.take())
        self.assertFalse(b.take())
        self.assertAlmostEqual(b.wait_s(), 1.0)
        clock.t += 1.5
        self.assertTrue(b.take())

    def test_per_phone_isolation_and_prune(self):
        clock = Clock()
        rl = RateLimiter(1, 0.1, clock, max_phones=2)
        self.assertTrue(rl.allow("a"))
        self.assertFalse(rl.allow("a"))
        self.assertTrue(rl.allow("b"))
        clock.t += 100
        self.assertTrue(rl.allow("c"))   # triggers prune of refilled buckets
        self.assertLessEqual(len(rl._buckets), 2)


class VoiceTests(unittest.TestCase):
    def test_lookup(self):
        self.assertIn("TZ482915", voicenote.transcribe({"id": "vn-wismo-1"}))
        with self.assertRaises(voicenote.TranscriptionError):
            voicenote.transcribe({"id": "nope"})
        with self.assertRaises(voicenote.TranscriptionError):
            voicenote.transcribe({"id": "vn-noise-1"})

    def test_transcribe_all_skips_non_audio(self):
        texts, failed = voicenote.transcribe_all([
            {"id": "vn-wismo-1", "kind": "audio"}, {"id": "img", "kind": "image"}, {"id": "zzz", "kind": "audio"}])
        self.assertEqual(len(texts), 1)
        self.assertEqual(failed, ["zzz"])


class FormattingTests(unittest.TestCase):
    def test_strip_markdown(self):
        out = formatting.strip_markdown("# Hi\n**bold** and *it* `code`\n- item\n[track](https://x.in/t)")
        self.assertEqual(out, "Hi\nbold and it code\n- item\ntrack (https://x.in/t)")

    def test_split_respects_limit(self):
        text = " ".join(["Sentence number %d is here." % i for i in range(60)])
        parts = formatting.split_reply(text, 100)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 100 for p in parts))
        self.assertEqual(" ".join(parts).split(), text.split())

    def test_hard_cut_for_long_word(self):
        parts = formatting.split_reply("x" * 250, 100)
        self.assertEqual([len(p) for p in parts], [100, 100, 50])

    def test_format_reply_drops_eta_line_and_maps_emoji(self):
        out = formatting.format_reply("It is on the way (truck) :)\nETA: tomorrow")
        self.assertEqual(len(out), 1)
        self.assertNotIn("ETA", out[0])
        self.assertIn("\U0001F69A", out[0])

    def test_quick_replies(self):
        self.assertEqual(formatting.quick_replies("which slot?", "hinglish"), ["Aaj", "Kal", "Parso"])
        self.assertEqual(formatting.quick_replies("hello"), [])

    def test_preview_and_collapse(self):
        self.assertEqual(formatting.preview("a  b\nc", 10), "a b c")
        self.assertTrue(formatting.preview("x" * 100, 10).endswith("..."))
        self.assertEqual(formatting.collapse_whitespace("a   b\n\n\n\nc"), "a b\n\nc")


class ConfigTests(unittest.TestCase):
    def test_env_overrides(self):
        cfg = GatewayConfig.from_env({
            "TEZDAK_GW_SESSION_TTL_S": "60", "TEZDAK_GW_RATE_REFILL_PER_S": "0.5",
            "TEZDAK_GW_STRIP_MARKDOWN": "off", "TEZDAK_GW_SESSION_FILE": "/tmp/x.json"})
        self.assertEqual((cfg.session_ttl_s, cfg.rate_refill_per_s, cfg.strip_markdown), (60, 0.5, False))
        self.assertEqual(cfg.session_file, "/tmp/x.json")
        self.assertEqual(GatewayConfig.from_env({}), GatewayConfig())

    def test_bad_value(self):
        with self.assertRaises(GatewayConfigError):
            GatewayConfig.from_env({"TEZDAK_GW_DEDUPE_CAPACITY": "lots"})


if __name__ == "__main__":
    unittest.main()
