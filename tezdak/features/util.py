"""Small helpers shared by the feature modules.

Kept deliberately boring: spec builders, duck-typed field access, time and
text helpers. Nothing here talks to the carrier or the backend on its own.
"""

import re
from datetime import date, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
AWB_RE = re.compile(r"\bTZ\d{6,}\b", re.I)
VPA_RE = re.compile(r"^[a-zA-Z0-9._-]{2,64}@[a-zA-Z]{2,32}$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

AWB_PROP = {"type": "string", "description": "Shipment AWB, for example TZ4829301"}


def tool_spec(name, description, properties, required):
    """Same function-tool shape as tezdak.tools.TOOL_SPECS."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(required)},
    }


def missing_args(spec_required, args):
    return [k for k in spec_required if args.get(k) in (None, "")]


def err(code, **extra):
    out = {"error": code}
    out.update(extra)
    return out


def field(obj, key, default=None):
    """Read `key` from a dict or an attribute-style row."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def now_of(ctx):
    if ctx.now is not None:
        return ctx.now
    cn = getattr(ctx.carrier, "now", None)
    return cn if isinstance(cn, datetime) else datetime.now(IST)


def parse_ts(value):
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=IST)
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def pick(ctx, english, hinglish):
    return hinglish if ctx.language == "hinglish" else english


def resolve_awb(ctx, args):
    awb = (args or {}).get("awb") or ctx.awb
    if not awb:
        m = AWB_RE.search(ctx.user_text or "")
        awb = m.group(0) if m else None
    return awb.upper() if awb else None


def friendly_date(d, today):
    """'today', 'tomorrow' or '4 Nov' for a date relative to today."""
    if isinstance(d, datetime):
        d = d.date()
    if isinstance(today, datetime):
        today = today.date()
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    return "%d %s" % (d.day, d.strftime("%b"))


def to_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and ISO_DATE_RE.match(value):
        return date.fromisoformat(value)
    return None


def safe_call(fn, *a, **kw):
    """Run a carrier/backend call. Returns (value, error_dict_or_None)."""
    try:
        return fn(*a, **kw), None
    except Exception as exc:  # carrier timeouts, backend errors: surface as data
        return None, {"error": "backend_call_failed", "kind": type(exc).__name__, "detail": str(exc)}


def ticket_id_of(created):
    """Backends return an int id; tolerate dict-shaped rows."""
    if isinstance(created, dict):
        return created.get("id")
    return created


def list_tickets(backend, **kw):
    try:
        return list(backend.tickets.list(**kw))
    except Exception:
        return []


def mask_phone(phone):
    digits = re.sub(r"\D", "", phone or "")
    return ("xxxxxx" + digits[-4:]) if len(digits) >= 4 else "unknown"


def money(amount):
    return "Rs %d" % int(amount)
