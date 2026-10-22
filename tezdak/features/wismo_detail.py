"""Richer where-is-my-order answer: status, attempts left, ETA window, last scan.

Changelog
  0.3  Hinglish phrasing tables split out of the builder.
  0.2  ETA window now depends on the 11:00 hub cutoff.
  0.1  Plain status line.

TODO: use the seller's promised date once orders carry it.
"""

from datetime import timedelta

from .base import Feature, FeatureContext
from .util import (AWB_PROP, err, field, friendly_date, now_of, parse_ts, pick, resolve_awb, safe_call, tool_spec)

CUTOFF_HOUR = 11
USE_SCAN_TEXT = True  # flag: include the latest scan line in the answer

STATUS_EN = {
    "OUT_FOR_DELIVERY": "out for delivery",
    "NDR": "held back after a missed delivery attempt",
    "RESCHEDULED": "rescheduled for another delivery attempt",
    "DELIVERED": "delivered",
    "RTO_INITIATED": "on its way back to the seller",
    "IN_TRANSIT": "in transit to your delivery hub",
}
STATUS_HI = {
    "OUT_FOR_DELIVERY": "delivery ke liye nikla hua hai",
    "NDR": "ek attempt miss hone ke baad ruka hua hai",
    "RESCHEDULED": "dobara delivery ke liye reschedule hua hai",
    "DELIVERED": "deliver ho chuka hai",
    "RTO_INITIATED": "seller ko wapas bheja ja raha hai",
    "IN_TRANSIT": "aapke hub ki taraf aa raha hai",
}


def attempts_left(shipment, policies):
    used = int(field(shipment, "attempts_used", 0) or 0)
    try:
        cap = int(policies.max_attempts())
    except Exception:
        cap = 3
    return max(cap - used, 0)


def eta_window(status, now, rescheduled_for=None):
    """Return (date or None, note). Purely a planning estimate, not a promise."""
    today = now.date()
    if status == "OUT_FOR_DELIVERY":
        return today, "by evening"
    if status == "RESCHEDULED":
        return (rescheduled_for or today + timedelta(days=1)), "between 9 AM and 8 PM"
    if status == "NDR":
        return None, "needs a new slot"
    if status == "IN_TRANSIT":
        return today + timedelta(days=1 if now.hour < CUTOFF_HOUR else 2), "after it reaches the hub"
    return None, ""


def last_scan_line(scans):
    rows = [s for s in (scans or []) if isinstance(s, dict) and s.get("ts")]
    if not rows:
        return None
    rows.sort(key=lambda s: s["ts"])
    last = rows[-1]
    return {"ts": last["ts"], "text": last.get("status_text") or last.get("status") or ""}


def build_summary(shipment, scans, now, policies, language="english"):
    status = field(shipment, "status", "UNKNOWN")
    hi = language == "hinglish"
    label = (STATUS_HI if hi else STATUS_EN).get(status, status.lower().replace("_", " "))
    eta, note = eta_window(status, now)
    left = attempts_left(shipment, policies)
    last = last_scan_line(scans) if USE_SCAN_TEXT else None
    if hi:
        line = "Aapka parcel abhi %s." % label
    else:
        line = "Your parcel is %s." % label
    if eta is not None:
        when = friendly_date(eta, now)
        line += " Expected %s, %s." % (when, note)
    elif note and status != "DELIVERED":
        line += " It %s." % note if not hi else " Isko %s." % note
    if status in ("NDR", "RESCHEDULED", "OUT_FOR_DELIVERY") and left is not None:
        line += (" %d delivery attempt(s) left." if not hi else " %d attempt baaki hai.") % left
    data = {"status": status, "attempts_left": left, "eta_date": eta.isoformat() if eta else None,
            "eta_note": note, "last_scan": last, "summary": line}
    return data


class WismoDetailFeature(Feature):
    name = "wismo_detail"
    intents = ("wismo",)

    def tool_specs(self):
        return [tool_spec("wismo_detail", "Full status answer for a shipment: status, ETA window, attempts left, last scan.",
                          {"awb": AWB_PROP}, ["awb"])]

    def run_tool(self, name, args, ctx: FeatureContext):
        if name != "wismo_detail":
            return err("unknown_tool", name=name)
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return e
        if not shipment or field(shipment, "error"):
            return err("shipment_not_found", awb=awb)
        scans, e2 = safe_call(ctx.carrier.get_scans, awb)
        if e2:
            scans = []
        out = build_summary(shipment, scans, now_of(ctx), ctx.policies, ctx.language)
        out["awb"] = awb
        return out

    def prompt_hint(self, ctx):
        return pick(ctx,
                    "Call wismo_detail once and read its summary to the customer. Do not promise a date it does not give.",
                    "wismo_detail ek baar call karo aur uska summary simple Hinglish mein batao. Jo date tool na de, woh promise mat karo.")
