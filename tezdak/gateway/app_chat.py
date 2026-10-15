"""In-app chat payloads and typing events."""

from datetime import datetime

from .message import IST, InboundMessage, OutboundMessage, normalize_phone


class AppChatError(ValueError):
    pass


def parse_app_payload(payload) -> InboundMessage:
    """App payload: {"user":{"phone","name"},"msg_id","text","attachments":[...],"sent_at"}."""
    if not isinstance(payload, dict):
        raise AppChatError("payload must be an object")
    user = payload.get("user") or {}
    phone = normalize_phone(user.get("phone"))
    if not phone:
        raise AppChatError("missing or invalid phone")
    ts = None
    if payload.get("sent_at"):
        try:
            ts = datetime.fromisoformat(payload["sent_at"])
        except ValueError:
            ts = None
    media = [
        {"id": a.get("id", ""), "kind": a.get("kind", "image"), "mime": a.get("mime", "")}
        for a in payload.get("attachments") or []
    ]
    kwargs = {"ts": ts.astimezone(IST) if ts and ts.tzinfo else ts} if ts else {}
    return InboundMessage(
        channel="app",
        phone=phone,
        text=str(payload.get("text") or "").strip(),
        media=media,
        message_id=str(payload.get("msg_id") or ""),
        sender_name=user.get("name", ""),
        **kwargs,
    )


def build_app_payload(msg: OutboundMessage) -> dict:
    return {
        "user": {"phone": msg.phone},
        "msg_id": msg.message_id,
        "reply_to": msg.in_reply_to,
        "text": msg.text,
        "quick_replies": [{"label": b, "value": b} for b in msg.buttons],
        "sent_at": msg.ts.isoformat(),
    }


def typing_event(phone, on=True) -> dict:
    return {"event": "typing", "user": {"phone": phone}, "state": "start" if on else "stop"}


def read_receipt(phone, message_id) -> dict:
    return {"event": "read", "user": {"phone": phone}, "msg_id": message_id}


def build_history_payload(phone, messages) -> dict:
    """Used when the app reopens a conversation and needs the last few turns."""
    return {
        "user": {"phone": phone},
        "history": [{"from": "me" if m.get("role") == "user" else "agent", "text": m.get("content", "")} for m in messages],
    }
