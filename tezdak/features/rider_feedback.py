"""Rider feedback: a 1 to 5 rating plus an optional comment, saved on a ticket.

The feedback is stored as a note, nothing is escalated or disputed from here.

Changelog
  0.2  One feedback ticket per AWB; later ratings append notes.
  0.1  Rating only.
"""

import re

from .base import Feature
from .templates import say
from .util import AWB_PROP, err, field, list_tickets, pick, resolve_awb, safe_call, ticket_id_of, tool_spec

KIND = "rider_feedback"
MAX_COMMENT = 400
RATING_RE = re.compile(r"\b([1-5])\s*(?:/\s*5|star|stars|out of 5)\b", re.I)
BAD_WORDS = ("idiot", "stupid")  # light masking only; nothing is blocked


def parse_rating(text):
    m = RATING_RE.search(text or "")
    return int(m.group(1)) if m else None


def clean_comment(text):
    t = " ".join((text or "").split())
    for w in BAD_WORDS:
        t = re.sub(w, "*" * len(w), t, flags=re.I)
    return t[:MAX_COMMENT]


def priority_for(rating):
    return "normal" if rating >= 3 else "high"


class RiderFeedbackFeature(Feature):
    name = "rider_feedback"
    intents = ("feedback",)

    def tool_specs(self):
        return [tool_spec("save_rider_feedback", "Save the customer's rating (1 to 5) and comment about the delivery rider.",
                          {"awb": AWB_PROP, "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                           "comment": {"type": "string"}}, ["awb", "rating"])]

    def run_tool(self, name, args, ctx):
        if name != "save_rider_feedback":
            return err("unknown_tool", name=name)
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        try:
            rating = int(args.get("rating"))
        except (TypeError, ValueError):
            return err("bad_arguments", detail="rating must be 1 to 5")
        if not 1 <= rating <= 5:
            return err("bad_arguments", detail="rating must be 1 to 5")
        comment = clean_comment(args.get("comment"))
        note = "rating=%d comment=%s" % (rating, comment or "-")
        existing = [t for t in list_tickets(ctx.backend, awb=awb) if field(t, "kind") == KIND]
        if existing:
            tid = field(existing[0], "id")
            _, e = safe_call(ctx.backend.tickets.add_note, tid, note, "customer")
            if e:
                return e
            return {"saved": True, "ticket_id": tid, "appended": True}
        tid, e = safe_call(ctx.backend.tickets.create, awb, KIND, "Rider feedback %d/5" % rating, priority_for(rating), "chat")
        if e:
            return e
        tid = ticket_id_of(tid)
        _, e = safe_call(ctx.backend.tickets.add_note, tid, note, "customer")
        if e:
            return e
        return {"saved": True, "ticket_id": tid, "appended": False, "customer_message": say("thanks_feedback", ctx.language)}

    def prompt_hint(self, ctx):
        return pick(ctx, "Ask for a rating from 1 to 5 and an optional comment, then call save_rider_feedback. Thank the customer.",
                    "1 se 5 ke beech rating poochho aur chaho to comment, phir save_rider_feedback call karo. Shukriya bolo.")
