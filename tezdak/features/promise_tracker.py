"""Record ETA commitments on the ticket store and flag the broken ones.

One ticket per commitment: kind `eta_promise`, summary `ETA <value>`. Outcomes
are matched by AWB when `evaluate_promises` is given delivery dates.

Changelog
  0.2  Duplicate promises for the same ETA are merged into the existing ticket.
  0.1  Record only.
"""

from datetime import timedelta

from .base import Feature
from .util import (AWB_PROP, ISO_DATE_RE, err, field, list_tickets, now_of, parse_ts, pick, resolve_awb, safe_call,
                   ticket_id_of, tool_spec, to_date)

KIND = "eta_promise"
PREFIX = "ETA "
GRACE_DAYS = 0
VALID_WORDS = ("today", "tomorrow")


def normalise_eta(value, now):
    """Return an ISO date string or None."""
    v = (value or "").strip().lower()
    if v == "today":
        return now.date().isoformat()
    if v == "tomorrow":
        return (now.date() + timedelta(days=1)).isoformat()
    if ISO_DATE_RE.match(v):
        return v
    return None


def promised_date(ticket):
    summary = field(ticket, "summary", "") or ""
    if not summary.startswith(PREFIX):
        return None
    return to_date(summary[len(PREFIX):].strip())


def evaluate(promises, outcomes, now):
    """promises: ticket rows. outcomes: {awb: delivered_iso_or_None}. Returns list of verdicts."""
    verdicts = []
    for t in promises:
        due = promised_date(t)
        if due is None:
            continue
        awb = field(t, "awb")
        delivered = to_date(outcomes.get(awb)) if awb in outcomes else None
        if delivered is not None:
            state = "kept" if delivered <= due + timedelta(days=GRACE_DAYS) else "broken"
        elif now.date() > due + timedelta(days=GRACE_DAYS):
            state = "broken"
        else:
            state = "pending"
        verdicts.append({"ticket_id": field(t, "id"), "awb": awb, "promised": due.isoformat(), "state": state})
    return verdicts


class PromiseTrackerFeature(Feature):
    name = "promise_tracker"
    intents = ("wismo", "reschedule_request", "ndr_complaint")

    def tool_specs(self):
        return [
            tool_spec("record_eta_promise", "Record the delivery date just promised to the customer.",
                      {"awb": AWB_PROP, "eta": {"type": "string", "description": "today, tomorrow or YYYY-MM-DD"}}, ["awb", "eta"]),
            tool_spec("check_promises", "Check recorded delivery promises for this AWB against what actually happened.",
                      {"awb": AWB_PROP}, ["awb"]),
        ]

    def _promises(self, awb, ctx):
        return [t for t in list_tickets(ctx.backend, awb=awb) if field(t, "kind") == KIND]

    def run_tool(self, name, args, ctx):
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        now = now_of(ctx)
        if name == "record_eta_promise":
            eta = normalise_eta(args.get("eta"), now)
            if not eta:
                return err("bad_arguments", detail="eta must be today, tomorrow or YYYY-MM-DD")
            for t in self._promises(awb, ctx):
                if promised_date(t) and promised_date(t).isoformat() == eta:
                    return {"recorded": False, "duplicate_of": field(t, "id"), "eta": eta}
            tid, e = safe_call(ctx.backend.tickets.create, awb, KIND, PREFIX + eta, "normal", "chat")
            if e:
                return e
            return {"recorded": True, "ticket_id": ticket_id_of(tid), "eta": eta}
        if name == "check_promises":
            promises = self._promises(awb, ctx)
            outcomes = {}
            shipment, e = safe_call(ctx.carrier.get_shipment, awb)
            if not e and field(shipment, "status") == "DELIVERED":
                scans, _ = safe_call(ctx.carrier.get_scans, awb)
                days = [parse_ts(s.get("ts")) for s in (scans or []) if isinstance(s, dict) and s.get("status") == "DELIVERED"]
                days = [d for d in days if d]
                outcomes[awb] = max(days).date().isoformat() if days else now.date().isoformat()
            verdicts = evaluate(promises, outcomes, now)
            return {"awb": awb, "promises": verdicts, "broken": [v for v in verdicts if v["state"] == "broken"]}
        return err("unknown_tool", name=name)

    def prompt_hint(self, ctx):
        return pick(ctx, "After you tell the customer a delivery date, call record_eta_promise with that same date.",
                    "Customer ko date batane ke baad wahi date record_eta_promise mein daalo.")
