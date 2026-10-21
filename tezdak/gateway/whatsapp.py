"""WhatsApp Cloud style webhook parsing and outbound payloads.

Changelog:
  v1  text messages only
  v2  media, interactive button replies
  v3  24 hour session window and template fallback
"""

from datetime import datetime, timedelta

from .message import IST, InboundMessage, OutboundMessage, normalize_phone

SESSION_WINDOW = timedelta(hours=24)
DEFAULT_TEMPLATE = "tezdak_followup_v2"
MEDIA_KINDS = ("image", "audio", "video", "document", "sticker")


class WebhookError(ValueError):
    pass


def _ts_from(raw):
    try:
        return datetime.fromtimestamp(int(raw), IST)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _one_message(msg, names):
    kind = msg.get("type", "text")
    phone = normalize_phone(msg.get("from"))
    if not phone:
        return None
    text, media = "", []
    if kind == "text":
        text = (msg.get("text") or {}).get("body", "")
    elif kind == "button":
        text = (msg.get("button") or {}).get("text", "")
    elif kind == "interactive":
        inter = msg.get("interactive") or {}
        reply = inter.get("button_reply") or inter.get("list_reply") or {}
        text = reply.get("title", "")
    elif kind in MEDIA_KINDS:
        body = msg.get(kind) or {}
        media.append({"id": body.get("id", ""), "kind": kind, "mime": body.get("mime_type", "")})
        text = body.get("caption", "")
    else:
        return None   # location, contacts, reactions: not handled
    return InboundMessage(
        channel="whatsapp",
        phone=phone,
        text=text.strip(),
        media=media,
        ts=_ts_from(msg.get("timestamp")) or datetime.now(IST),
        message_id=msg.get("id", ""),
        sender_name=names.get(msg.get("from"), ""),
    )


def parse_webhook(payload) -> list:
    """Parse a webhook body into InboundMessage objects. Status-only callbacks give []."""
    if not isinstance(payload, dict) or "entry" not in payload:
        raise WebhookError("not a whatsapp webhook payload")
    out = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts") or []}
            for msg in value.get("messages") or []:
                parsed = _one_message(msg, names)
                if parsed is not None:
                    out.append(parsed)
    return out


def window_open(last_inbound_ts, now) -> bool:
    """Free-form (session) messages are allowed only within 24h of the customer's last message."""
    if last_inbound_ts is None:
        return False
    return now - last_inbound_ts < SESSION_WINDOW


def build_text_payload(msg: OutboundMessage) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": msg.phone,
        "type": "text",
        "text": {"body": msg.text, "preview_url": False},
    }


def build_buttons_payload(msg: OutboundMessage) -> dict:
    buttons = [
        {"type": "reply", "reply": {"id": "btn_%d" % i, "title": label[:20]}}
        for i, label in enumerate(msg.buttons[:3])
    ]
    return {
        "messaging_product": "whatsapp",
        "to": msg.phone,
        "type": "interactive",
        "interactive": {"type": "button", "body": {"text": msg.text}, "action": {"buttons": buttons}},
    }


def build_template_payload(msg: OutboundMessage, params=None) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": msg.phone,
        "type": "template",
        "template": {
            "name": msg.template or DEFAULT_TEMPLATE,
            "language": {"code": "en"},
            "components": [{"type": "body", "parameters": [{"type": "text", "text": str(p)} for p in (params or [msg.text])]}],
        },
    }


def build_payload(msg: OutboundMessage, last_inbound_ts, now) -> dict:
    """Choose session vs template. Outside the window only templates may be sent."""
    if window_open(last_inbound_ts, now):
        return build_buttons_payload(msg) if msg.buttons else build_text_payload(msg)
    return build_template_payload(msg)


# -- delivery status callbacks and webhook verification (v3) -------------------

STATUS_ORDER = {"sent": 1, "delivered": 2, "read": 3, "failed": 0}


def parse_statuses(payload) -> list:
    """Delivery receipts: [{"message_id","phone","status","ts","error"}]."""
    out = []
    for entry in (payload or {}).get("entry") or []:
        for change in entry.get("changes") or []:
            for st in (change.get("value") or {}).get("statuses") or []:
                errors = st.get("errors") or [{}]
                out.append({
                    "message_id": st.get("id", ""),
                    "phone": normalize_phone(st.get("recipient_id")),
                    "status": st.get("status", ""),
                    "ts": _ts_from(st.get("timestamp")),
                    "error": errors[0].get("title", "") if st.get("status") == "failed" else "",
                })
    return out


def best_status(statuses) -> str:
    """Highest-ranked receipt seen for one message; 'failed' only wins when nothing else arrived."""
    ranked = sorted((s for s in statuses if s in STATUS_ORDER), key=STATUS_ORDER.get)
    return ranked[-1] if ranked else ""


def verify_challenge(params, verify_token) -> str:
    """GET handshake: return the challenge string, or raise WebhookError."""
    if params.get("hub.mode") == "subscribe" and params.get("hub.verify_token") == verify_token:
        return str(params.get("hub.challenge", ""))
    raise WebhookError("verification failed")


def verify_signature(body: bytes, header: str, app_secret: str) -> bool:
    """Check the `X-Hub-Signature-256: sha256=<hex>` header."""
    import hashlib
    import hmac

    if not header or not header.startswith("sha256=") or not app_secret:
        return False
    digest = hmac.new(app_secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header[len("sha256="):])
