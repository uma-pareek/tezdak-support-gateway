"""Human handoff: one ticket with a summary the next person can read in ten seconds.

Only writes to the ticket store. No carrier calls that change anything.

Changelog
  0.2  Summary lists the tickets already open for the AWB.
  0.1  Reason + shipment line.
"""

from .base import Feature
from .templates import say
from .util import (AWB_PROP, err, field, list_tickets, mask_phone, missing_args, money, now_of, resolve_awb, safe_call,
                   ticket_id_of, tool_spec)

KIND = "handoff"
HIGH_VALUE_INR = 3000
REASONS = ("customer_asked", "policy_limit", "unclear", "angry_customer", "other")
URGENT_WORDS = ("legal", "consumer court", "police", "fraud", "scam")


def priority_for(reason, amount, user_text):
    text = (user_text or "").lower()
    if any(w in text for w in URGENT_WORDS):
        return "urgent"
    if reason in ("angry_customer", "policy_limit") or (amount or 0) >= HIGH_VALUE_INR:
        return "high"
    return "normal"


def build_summary(awb, reason, shipment, open_tickets, user_text, language, note=None):
    parts = ["Handoff for %s (%s)." % (awb, reason)]
    if shipment and not field(shipment, "error"):
        parts.append("Status %s, attempts used %s, %s %s, pincode %s, phone %s." % (
            field(shipment, "status"), field(shipment, "attempts_used"), field(shipment, "payment_mode"),
            money(field(shipment, "amount_inr", 0) or 0), field(shipment, "pincode"), mask_phone(field(shipment, "phone"))))
    if open_tickets:
        parts.append("Open tickets: " + ", ".join("#%s %s" % (field(t, "id"), field(t, "kind")) for t in open_tickets[:5]) + ".")
    parts.append("Customer wrote (%s): %s" % (language, " ".join((user_text or "").split())[:200]))
    if note:
        parts.append("Agent note: %s" % note[:200])
    return " ".join(parts)


class HandoffFeature(Feature):
    name = "handoff"
    intents = ("other", "handoff_request")

    def tool_specs(self):
        return [tool_spec("create_handoff", "Hand this chat to a human with a readable summary. Creates a ticket.",
                          {"awb": AWB_PROP, "reason": {"type": "string", "enum": list(REASONS)},
                           "note": {"type": "string"}}, ["awb", "reason"])]

    def can_handle(self, ctx):
        text = (ctx.user_text or "").lower()
        wants = any(w in text for w in ("human", "agent", "manager", "insaan", "bande se"))
        return wants or ctx.intent in self.intents and "human" in text

    def run_tool(self, name, args, ctx):
        if name != "create_handoff":
            return err("unknown_tool", name=name)
        awb = resolve_awb(ctx, args)
        miss = missing_args(["reason"], args)
        if not awb or miss:
            return err("bad_arguments", missing=miss or ["awb"])
        reason = args["reason"] if args["reason"] in REASONS else "other"
        for t in list_tickets(ctx.backend, awb=awb, status="open"):
            if field(t, "kind") == KIND:
                return {"created": False, "ticket_id": field(t, "id"), "already_open": True}
        shipment, _ = safe_call(ctx.carrier.get_shipment, awb)
        others = list_tickets(ctx.backend, awb=awb, status="open")
        summary = build_summary(awb, reason, shipment, others, ctx.user_text, ctx.language, args.get("note"))
        amount = field(shipment, "amount_inr", 0) if shipment else 0
        tid, e = safe_call(ctx.backend.tickets.create, awb, KIND, summary, priority_for(reason, amount, ctx.user_text), "chat")
        if e:
            return e
        return {"created": True, "ticket_id": ticket_id_of(tid), "summary": summary,
                "customer_message": say("handoff_done", ctx.language)}

    def prompt_hint(self, ctx):
        return "When the customer asks for a human or the case is outside what you can do, call create_handoff once and say a colleague will follow up."
