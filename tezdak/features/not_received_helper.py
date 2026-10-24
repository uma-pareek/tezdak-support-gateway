"""Guided questions for parcels marked delivered that the customer says they did not get.

The helper only gathers facts and records an intake ticket. It never opens a
dispute and never issues money; the agent decides what to do with the answers.

Changelog
  0.2  Question order depends on whether the order needed an OTP.
  0.1  Fixed list of questions.
"""

from .base import Feature
from .util import AWB_PROP, err, field, list_tickets, pick, resolve_awb, safe_call, ticket_id_of, tool_spec

KIND = "not_received_intake"

QUESTIONS = {
    "checked_neighbours": ("Have you checked with family, neighbours or the security desk?",
                           "Kya aapne ghar walon, padosiyon ya security se pooch liya?"),
    "address_correct": ("Is the address on the order correct?", "Kya order par diya address sahi hai?"),
    "otp_shared": ("Did you share any OTP with the rider?", "Kya aapne rider ko koi OTP bataya tha?"),
    "delivery_time_seen": ("Did you get a delivery message or call around the time it was marked delivered?",
                           "Delivered mark hone ke aas-paas koi message ya call aaya tha?"),
}
BASE_ORDER = ["checked_neighbours", "address_correct", "delivery_time_seen"]
YES = ("yes", "y", "haan", "han", "ha", "yep", "true")
NO = ("no", "n", "nahi", "nahin", "nai", "false")


def question_order(otp_required):
    order = list(BASE_ORDER)
    if otp_required:
        order.insert(0, "otp_shared")
    return order


def norm_answer(v):
    t = str(v).strip().lower()
    if t in YES:
        return "yes"
    if t in NO:
        return "no"
    return "unclear"


def next_step(answers, otp_required):
    clean = {k: norm_answer(v) for k, v in (answers or {}).items() if k in QUESTIONS}
    for key in question_order(otp_required):
        if key not in clean:
            return {"done": False, "ask": key, "answers": clean}
    return {"done": True, "answers": clean}


def observations(answers, otp_required):
    notes = []
    if answers.get("checked_neighbours") == "no":
        notes.append("Customer has not checked with neighbours yet; suggest it first.")
    if answers.get("address_correct") == "no":
        notes.append("Address on the order is wrong.")
    if otp_required and answers.get("otp_shared") == "yes":
        notes.append("Customer says an OTP was shared with the rider.")
    if answers.get("delivery_time_seen") == "no":
        notes.append("No delivery message or call was noticed.")
    return notes


class NotReceivedHelperFeature(Feature):
    name = "not_received_helper"
    intents = ("not_received_after_delivered",)

    def tool_specs(self):
        keys = sorted(QUESTIONS)
        return [tool_spec("not_received_next_question",
                          "Get the next fact-gathering question for a parcel marked delivered but not received. "
                          "Pass the answers collected so far, keyed by question id.",
                          {"awb": AWB_PROP,
                           "answers": {"type": "object", "description": "question id -> customer answer. Ids: " + ", ".join(keys)}},
                          ["awb"])]

    def run_tool(self, name, args, ctx):
        if name != "not_received_next_question":
            return err("unknown_tool", name=name)
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return e
        if not shipment or field(shipment, "error"):
            return err("shipment_not_found", awb=awb)
        if field(shipment, "status") != "DELIVERED":
            return {"applicable": False, "status": field(shipment, "status")}
        otp = bool(field(shipment, "otp_required", False))
        answers = args.get("answers") if isinstance(args.get("answers"), dict) else {}
        step = next_step(answers, otp)
        if not step["done"]:
            en, hi = QUESTIONS[step["ask"]]
            return {"applicable": True, "done": False, "ask": step["ask"], "question": pick(ctx, en, hi)}
        notes = observations(step["answers"], otp)
        existing = [t for t in list_tickets(ctx.backend, awb=awb) if field(t, "kind") == KIND]
        if existing:
            tid = field(existing[0], "id")
        else:
            tid, e = safe_call(ctx.backend.tickets.create, awb, KIND, "Not-received intake: " + "; ".join(notes or ["no flags"]),
                               "normal", "chat")
            if e:
                return e
            tid = ticket_id_of(tid)
        return {"applicable": True, "done": True, "answers": step["answers"], "observations": notes, "ticket_id": tid}

    def prompt_hint(self, ctx):
        return ("Ask one question at a time using not_received_next_question until it says done. Do not promise a refund "
                "or open any complaint with the carrier from this flow; summarise the answers for the customer.")
