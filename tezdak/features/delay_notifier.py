"""Proactive delay message planner. Produces messages; sending is someone else's job.

Changelog
  0.3  Reasons ranked so a customer gets one message per parcel per run.
  0.2  Hinglish templates.
  0.1  Stuck-in-transit rule only.

TODO: skip customers who opted out once the customer store has the flag.
"""

from datetime import timedelta

from .base import Feature
from .util import (AWB_PROP, err, field, friendly_date, mask_phone, now_of, parse_ts, pick, resolve_awb, safe_call,
                   tool_spec)

STUCK_HOURS = 36
OFD_LATE_HOUR = 18
MAX_PER_RUN = 500

TEMPLATES = {
    "stuck_in_transit": {
        "english": "Hi, your parcel {awb} is taking longer than usual to reach your city. We are chasing it and will update you by {by}.",
        "hinglish": "Hi, aapka parcel {awb} aapke sheher pahunchne mein thoda late hai. Hum follow up kar rahe hain, {by} tak update denge.",
    },
    "ofd_late": {
        "english": "Hi, parcel {awb} is still out for delivery and may reach you late today. Reply here if you want a new slot.",
        "hinglish": "Hi, parcel {awb} abhi bhi delivery ke liye nikla hua hai aur aaj der se pahunch sakta hai. Naya slot chahiye to yahin reply kijiye.",
    },
    "missed_attempt": {
        "english": "Hi, we could not deliver parcel {awb}. Reply here and we will book another attempt.",
        "hinglish": "Hi, parcel {awb} deliver nahi ho paaya. Yahin reply kijiye, hum dobara attempt book kar denge.",
    },
    "slot_passed": {
        "english": "Hi, your rescheduled slot for parcel {awb} has passed without delivery. Sorry about that; reply to pick a new slot.",
        "hinglish": "Hi, parcel {awb} ka reschedule slot nikal gaya aur delivery nahi hui. Maaf kijiye; naya slot batane ke liye reply kijiye.",
    },
}
PRIORITY = ["slot_passed", "missed_attempt", "ofd_late", "stuck_in_transit"]


def detect_reason(shipment, now, last_scan_ts=None, slot_date=None):
    status = field(shipment, "status")
    if status == "RESCHEDULED" and slot_date is not None and slot_date < now.date():
        return "slot_passed"
    if status == "NDR":
        return "missed_attempt"
    if status == "OUT_FOR_DELIVERY" and now.hour >= OFD_LATE_HOUR:
        return "ofd_late"
    if status == "IN_TRANSIT" and last_scan_ts is not None and now - last_scan_ts >= timedelta(hours=STUCK_HOURS):
        return "stuck_in_transit"
    return None


def render(reason, awb, language, now):
    tpl = TEMPLATES[reason]["hinglish" if language == "hinglish" else "english"]
    return tpl.format(awb=awb, by=friendly_date(now.date() + timedelta(days=1), now))


def plan_messages(items, now, default_language="english"):
    """items: list of dicts {shipment: {...}, last_scan_ts?, slot_date?, language?}. Returns message plans."""
    plans = []
    seen = set()
    for item in items:
        if len(plans) >= MAX_PER_RUN:
            break
        sh = item.get("shipment") or item
        awb = field(sh, "awb")
        if not awb or awb in seen:
            continue
        seen.add(awb)
        reason = detect_reason(sh, now, parse_ts(item.get("last_scan_ts")), item.get("slot_date"))
        if reason is None:
            continue
        lang = item.get("language") or default_language
        plans.append({"awb": awb, "reason": reason, "language": lang, "phone": field(sh, "phone"),
                      "phone_masked": mask_phone(field(sh, "phone")), "text": render(reason, awb, lang, now),
                      "rank": PRIORITY.index(reason)})
    plans.sort(key=lambda p: (p["rank"], p["awb"]))
    return plans


class DelayNotifierFeature(Feature):
    name = "delay_notifier"
    intents = ("delay_update",)

    def tool_specs(self):
        return [tool_spec("plan_delay_message", "Draft the proactive delay message for one parcel, if it is delayed. Does not send.",
                          {"awb": AWB_PROP}, ["awb"])]

    def run_tool(self, name, args, ctx):
        if name != "plan_delay_message":
            return err("unknown_tool", name=name)
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return e
        if not shipment or field(shipment, "error"):
            return err("shipment_not_found", awb=awb)
        scans, e = safe_call(ctx.carrier.get_scans, awb)
        times = [parse_ts(s.get("ts")) for s in (scans or []) if isinstance(s, dict) and s.get("ts")]
        last = max([t for t in times if t], default=None)
        plans = plan_messages([{"shipment": dict(shipment, awb=awb), "last_scan_ts": last, "language": ctx.language}],
                              now_of(ctx), ctx.language)
        if not plans:
            return {"delayed": False, "awb": awb}
        p = plans[0]
        return {"delayed": True, "awb": awb, "reason": p["reason"], "message": p["text"]}

    def prompt_hint(self, ctx):
        return pick(ctx, "Use plan_delay_message to see whether the parcel is delayed and apologise once, briefly.",
                    "plan_delay_message se dekho parcel late hai ya nahi, aur ek baar chhota sa sorry bolo.")
