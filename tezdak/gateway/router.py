"""Gateway entry point: raw channel payload in, formatted outbound messages out.

Changelog:
  v1  dedupe + session + agent call
  v2  rate limit, voice notes
  v3  template fallback outside the WhatsApp window (decided at send time, see `payload_for`)
"""

import time
from datetime import datetime

from . import app_chat, voicenote, whatsapp
from .config import GatewayConfig
from .dedupe import Deduper
from .formatting import format_reply, quick_replies
from .message import IST, InboundMessage, OutboundMessage
from .ratelimit import RateLimiter
from .sessions import SessionStore

HINGLISH_CUES = ("nahi", "kahan", "kab", "mera", "bhai", "karo", "hai", "aaya")
AGENT_FAILED_REPLY = "Sorry, kuch gadbad ho gayi. A colleague will follow up with you shortly."


class Gateway:
    def __init__(self, agent_handle, config=None, sessions=None, clock=time.time, on_event=None):
        self.agent_handle = agent_handle
        self.config = config or GatewayConfig()
        self.clock = clock
        self.on_event = on_event
        self.sessions = sessions or SessionStore(
            ttl_s=self.config.session_ttl_s,
            window=self.config.session_window,
            path=self.config.session_file,
            clock=clock,
        )
        self.deduper = Deduper(self.config.dedupe_capacity, self.config.dedupe_ttl_s)
        self.limiter = RateLimiter(self.config.rate_capacity, self.config.rate_refill_per_s)
        self.stats = {"received": 0, "duplicates": 0, "rate_limited": 0, "voice_failed": 0, "agent_errors": 0}

    def _emit(self, kind, **data):
        if self.on_event:
            self.on_event(kind, data)

    # -- parsing ---------------------------------------------------------
    def parse(self, raw, channel) -> list:
        if channel == "whatsapp":
            return whatsapp.parse_webhook(raw)
        if channel == "app":
            return [app_chat.parse_app_payload(raw)]
        raise ValueError("unknown channel %r" % (channel,))

    # -- main entry ------------------------------------------------------
    def on_message(self, raw, channel) -> list:
        out = []
        for inbound in self.parse(raw, channel):
            out.extend(self._handle_one(inbound))
        return out

    def _handle_one(self, inbound: InboundMessage) -> list:
        self.stats["received"] += 1
        if self.deduper.seen("%s:%s" % (inbound.channel, inbound.message_id)):
            self.stats["duplicates"] += 1
            self._emit("duplicate", message_id=inbound.message_id)
            return []
        if not self.limiter.allow(inbound.phone):
            self.stats["rate_limited"] += 1
            self._emit("rate_limited", phone=inbound.phone)
            return [self._reply(inbound, self.config.rate_limited_reply)]

        text = self._resolve_text(inbound)
        if text is None:
            self.stats["voice_failed"] += 1
            return [self._reply(inbound, self.config.voice_failed_reply)]

        sess = self.sessions.add_message(inbound.phone, "user", text, inbound.channel, inbound=True)
        try:
            result = self.agent_handle(sess.to_conversation())
        except Exception as exc:   # the gateway must always answer something
            self.stats["agent_errors"] += 1
            self._emit("agent_error", error=repr(exc))
            return [self._reply(inbound, AGENT_FAILED_REPLY)]

        reply_text = _reply_text(result)
        self.sessions.add_message(inbound.phone, "assistant", reply_text, inbound.channel)
        return self._format(inbound, reply_text, _language_of(text))

    def _resolve_text(self, inbound):
        """Text to feed the agent; audio is transcribed when voice notes are enabled."""
        if not inbound.has_audio:
            return inbound.text
        if not self.config.voice_notes_enabled:
            return inbound.text or None
        texts, failed = voicenote.transcribe_all(inbound.media)
        parts = ([inbound.text] if inbound.text else []) + texts
        if failed and not parts:
            return None
        return " ".join(parts)

    # -- outbound --------------------------------------------------------
    def _reply(self, inbound, text, buttons=None) -> OutboundMessage:
        return OutboundMessage(
            channel=inbound.channel, phone=inbound.phone, text=text,
            buttons=buttons or [], in_reply_to=inbound.message_id,
        )

    def _format(self, inbound, reply_text, language) -> list:
        limit = self.config.max_reply_chars if inbound.channel == "whatsapp" else 4000
        parts = format_reply(reply_text, self.config.strip_markdown, self.config.use_emoji_map, limit)
        if not parts:
            parts = [AGENT_FAILED_REPLY]
        msgs = [self._reply(inbound, p) for p in parts]
        msgs[-1].buttons = quick_replies(parts[-1], language)
        return msgs

    def send_proactive(self, phone, text, channel="whatsapp", template="") -> list:
        """Outbound-initiated message (delay notices etc). Not routed through the agent."""
        phone_ok = phone if phone.isdigit() else ""
        if not phone_ok:
            raise ValueError("phone must be digits only, got %r" % (phone,))
        parts = format_reply(text, self.config.strip_markdown, self.config.use_emoji_map, self.config.max_reply_chars)
        return [OutboundMessage(channel=channel, phone=phone, text=p, template=template) for p in parts]

    def snapshot(self) -> dict:
        return dict(self.stats, sessions=len(self.sessions), dedupe_entries=len(self.deduper))

    def payload_for(self, msg: OutboundMessage, now=None) -> dict:
        """Wire payload for an outbound message on its channel."""
        if msg.channel == "app":
            return app_chat.build_app_payload(msg)
        sess = self.sessions.get(msg.phone)
        last = datetime.fromtimestamp(sess.last_inbound_ts, IST) if sess and sess.last_inbound_ts else None
        return whatsapp.build_payload(msg, last, now or datetime.fromtimestamp(self.clock(), IST))


def _reply_text(result) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        return str(result.get("reply", ""))
    return str(getattr(result, "reply", "") or "")


def _language_of(text) -> str:
    low = (text or "").lower()
    return "hinglish" if any(c in low.split() for c in HINGLISH_CUES) else "english"
