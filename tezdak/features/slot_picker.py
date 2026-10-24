"""Offer delivery slots and book the one the customer picks.

Respects the hub cutoff: a same-day slot is only offered before 11:00 IST.

Changelog
  0.3  Evening window removed for tier3 pincodes.
  0.2  Cutoff text added to the answer.
  0.1  Tomorrow-only slots.
"""

from datetime import date, timedelta

from .base import Feature
from .util import AWB_PROP, ISO_DATE_RE, err, field, friendly_date, now_of, pick, resolve_awb, safe_call, tool_spec

CUTOFF_HOUR = 11
CUTOFF_TEXT = "Same-day slots close at 11:00 AM; after that the next slot is tomorrow."
CUTOFF_TEXT_HI = "Aaj ka slot subah 11:00 baje tak hi milta hai; uske baad agla slot kal ka hota hai."
WINDOWS = {"morning": "9 AM - 1 PM", "afternoon": "1 PM - 5 PM", "evening": "5 PM - 8 PM"}
TIER3_WINDOWS = ("morning", "afternoon")
DAYS_AHEAD = 3
BLOCKED_STATUSES = ("DELIVERED", "RTO_INITIATED")


def build_slots(now, tier=None, days_ahead=DAYS_AHEAD):
    windows = TIER3_WINDOWS if tier == "tier3" else tuple(WINDOWS)
    out = []
    first = 0 if now.hour < CUTOFF_HOUR else 1
    for offset in range(first, days_ahead + 1):
        d = now.date() + timedelta(days=offset)
        key = "today" if offset == 0 else ("tomorrow" if offset == 1 else d.isoformat())
        out.append({"slot": key, "date": d.isoformat(), "label": friendly_date(d, now), "windows": [
            {"name": w, "time": WINDOWS[w]} for w in windows]})
    return out


def valid_slot(slot, now):
    if slot == "today":
        return now.hour < CUTOFF_HOUR
    if slot == "tomorrow":
        return True
    if isinstance(slot, str) and ISO_DATE_RE.match(slot):
        try:
            target = date.fromisoformat(slot)
        except ValueError:
            return False
        today = now.date()
        if target == today:
            return now.hour < CUTOFF_HOUR
        return today < target <= today + timedelta(days=DAYS_AHEAD)
    return False


class SlotPickerFeature(Feature):
    name = "slot_picker"
    intents = ("reschedule_request",)

    def tool_specs(self):
        return [
            tool_spec("list_delivery_slots", "List delivery slots the customer can choose from, with the cutoff rule.",
                      {"awb": AWB_PROP}, ["awb"]),
            tool_spec("book_delivery_slot", "Book the slot the customer chose (today, tomorrow or an ISO date).",
                      {"awb": AWB_PROP, "slot": {"type": "string"}}, ["awb", "slot"]),
        ]

    def run_tool(self, name, args, ctx):
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        if name not in ("list_delivery_slots", "book_delivery_slot"):
            return err("unknown_tool", name=name)
        now = now_of(ctx)
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return e
        if not shipment or field(shipment, "error"):
            return err("shipment_not_found", awb=awb)
        status = field(shipment, "status")
        if status in BLOCKED_STATUSES:
            return err("not_reschedulable", status=status)
        used = int(field(shipment, "attempts_used", 0) or 0)
        cap = int(ctx.policies.max_attempts())
        if name == "list_delivery_slots":
            return {"slots": build_slots(now, field(shipment, "tier")), "cutoff_note": pick(ctx, CUTOFF_TEXT, CUTOFF_TEXT_HI),
                    "attempts_left": max(cap - used, 0), "last_attempt": used >= cap - 1}
        slot = str(args.get("slot", "")).strip().lower()
        if not slot:
            return err("bad_arguments", missing=["slot"])
        if not valid_slot(slot, now):
            return err("slot_not_available", cutoff_note=pick(ctx, CUTOFF_TEXT, CUTOFF_TEXT_HI),
                       offer=[s["slot"] for s in build_slots(now, field(shipment, "tier"))])
        res, e = safe_call(ctx.carrier.reschedule, awb, slot)
        if e:
            return e
        if isinstance(res, dict) and res.get("error"):
            return err("reschedule_failed", detail=str(res["error"]))
        return {"booked": True, "requested": slot, "result": res}

    def prompt_hint(self, ctx):
        return ("Call list_delivery_slots, offer only those slots, mention the 11:00 AM cutoff in one short line, "
                "then call book_delivery_slot once for the slot chosen. If it is the last attempt, say so.")
