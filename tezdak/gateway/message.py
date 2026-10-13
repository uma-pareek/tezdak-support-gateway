"""Channel-neutral message types."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
CHANNELS = ("whatsapp", "app")


def now_ist() -> datetime:
    return datetime.now(IST)


def normalize_phone(raw) -> str:
    """Digits only, Indian numbers as 91XXXXXXXXXX. Returns '' when unusable."""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    elif len(digits) == 11 and digits.startswith("0"):
        digits = "91" + digits[1:]
    return digits if len(digits) == 12 and digits.startswith("91") else ""


@dataclass
class InboundMessage:
    channel: str
    phone: str
    text: str = ""
    media: list = field(default_factory=list)   # [{"id","kind","mime"}]
    ts: datetime = field(default_factory=now_ist)
    message_id: str = ""
    sender_name: str = ""

    def __post_init__(self):
        if self.channel not in CHANNELS:
            raise ValueError("unknown channel %r" % (self.channel,))
        if self.ts.tzinfo is None:
            self.ts = self.ts.replace(tzinfo=IST)
        if not self.message_id:
            self.message_id = "gen-" + uuid.uuid4().hex[:12]

    @property
    def has_audio(self) -> bool:
        return any(m.get("kind") == "audio" for m in self.media)


@dataclass
class OutboundMessage:
    channel: str
    phone: str
    text: str = ""
    media: list = field(default_factory=list)
    ts: datetime = field(default_factory=now_ist)
    message_id: str = ""
    buttons: list = field(default_factory=list)   # quick replies, max 3
    template: str = ""                            # template name when sent outside the window
    in_reply_to: str = ""

    def __post_init__(self):
        if self.ts.tzinfo is None:
            self.ts = self.ts.replace(tzinfo=IST)
        if not self.message_id:
            self.message_id = "out-" + uuid.uuid4().hex[:12]


def mask_phone(phone: str) -> str:
    """For logs: keep the country code and last two digits."""
    phone = str(phone or "")
    return phone[:2] + "*" * max(0, len(phone) - 4) + phone[-2:] if len(phone) > 4 else "****"


def inbound_to_dict(msg: InboundMessage) -> dict:
    return {
        "channel": msg.channel, "phone": mask_phone(msg.phone), "text": msg.text,
        "media": list(msg.media), "ts": msg.ts.isoformat(), "message_id": msg.message_id,
    }
