"""COD refunds paid out to a UPI id.

Refund rules for this feature: a 5 day window after delivery and a 2000 rupee
limit before a human has to approve. Values are module constants.

Changelog
  0.3  VPA format check before calling the carrier.
  0.2  Over-limit claims create an approval ticket instead of paying.
  0.1  Window check only.
"""

from datetime import timedelta

from .base import Feature
from .util import (AWB_PROP, VPA_RE, err, field, money, now_of, parse_ts, pick, resolve_awb, safe_call, tool_spec,
                   ticket_id_of)

REFUND_WINDOW_DAYS = 5
APPROVAL_LIMIT_INR = 2000
UPI_FEE_INR = 6
MIN_REFUND_INR = 10
DEFAULT_KIND = "refund"


def delivered_at(scans):
    rows = [s for s in (scans or []) if isinstance(s, dict) and s.get("status") == "DELIVERED" and s.get("ts")]
    if not rows:
        return None
    return max(parse_ts(r["ts"]) for r in rows)


def check_claim(shipment, scans, amount, now):
    """Return (ok, reason, details)."""
    if field(shipment, "payment_mode") != "COD":
        return False, "not_cod", {}
    if field(shipment, "status") != "DELIVERED":
        return False, "not_delivered", {}
    paid = int(field(shipment, "amount_inr", 0) or 0)
    if amount < MIN_REFUND_INR:
        return False, "amount_too_small", {}
    if amount > paid:
        return False, "amount_exceeds_order", {"order_value_inr": paid}
    when = delivered_at(scans)
    if when is None:
        return False, "delivery_date_unknown", {}
    days = (now - when).days
    if days > REFUND_WINDOW_DAYS:
        return False, "outside_window", {"days_since_delivery": days, "window_days": REFUND_WINDOW_DAYS}
    return True, "ok", {"days_since_delivery": days, "window_days": REFUND_WINDOW_DAYS}


class CodRefundFeature(Feature):
    name = "cod_refund"
    intents = ("refund_status", "refund_request")

    def tool_specs(self):
        return [
            tool_spec("cod_refund_check", "Check whether a COD refund of this amount is allowed and who must approve it.",
                      {"awb": AWB_PROP, "amount_inr": {"type": "integer"}}, ["awb", "amount_inr"]),
            tool_spec("cod_refund_payout", "Pay a COD refund to the customer's UPI id.",
                      {"awb": AWB_PROP, "amount_inr": {"type": "integer"},
                       "vpa": {"type": "string", "description": "Customer UPI id such as name@upi"}},
                      ["awb", "amount_inr", "vpa"]),
        ]

    def _evaluate(self, awb, amount, ctx):
        try:
            amount = int(amount)
        except (TypeError, ValueError):
            return None, err("bad_arguments", detail="amount_inr must be a whole number")
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return None, e
        if not shipment or field(shipment, "error"):
            return None, err("shipment_not_found", awb=awb)
        scans, e = safe_call(ctx.carrier.get_scans, awb)
        if e:
            return None, e
        ok, why, det = check_claim(shipment, scans, amount, now_of(ctx))
        needs_human = amount > APPROVAL_LIMIT_INR
        return {"amount": amount, "ok": ok, "reason": why, "details": det, "needs_human": needs_human}, None

    def run_tool(self, name, args, ctx):
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        if name not in ("cod_refund_check", "cod_refund_payout"):
            return err("unknown_tool", name=name)
        ev, e = self._evaluate(awb, args.get("amount_inr"), ctx)
        if e:
            return e
        if name == "cod_refund_check":
            return {"allowed": ev["ok"], "reason": ev["reason"], "needs_human": ev["needs_human"],
                    "limit_inr": APPROVAL_LIMIT_INR, "window_days": REFUND_WINDOW_DAYS, "fee_inr": UPI_FEE_INR,
                    "details": ev["details"]}
        vpa = (args.get("vpa") or "").strip()
        if not VPA_RE.match(vpa):
            return err("invalid_vpa", message=pick(ctx, "That UPI id looks wrong. Please send it again.",
                                                   "Yeh UPI id sahi nahi lag raha. Dobara bhej dijiye."))
        if not ev["ok"]:
            return {"paid": False, "reason": ev["reason"], "details": ev["details"]}
        if ev["needs_human"]:
            tid, te = safe_call(ctx.backend.tickets.create, awb, "refund_approval",
                                "COD refund %s needs approval (limit %s)" % (money(ev["amount"]), money(APPROVAL_LIMIT_INR)),
                                "high", "chat")
            return {"paid": False, "reason": "needs_human_approval", "limit_inr": APPROVAL_LIMIT_INR,
                    "ticket_id": None if te else ticket_id_of(tid)}
        res, e = safe_call(ctx.carrier.create_refund, awb, ev["amount"], DEFAULT_KIND, vpa=vpa)
        if e:
            return e
        if isinstance(res, dict) and res.get("error"):
            return {"paid": False, "reason": str(res["error"]).lower()}
        safe_call(ctx.backend.tickets.create, awb, "cod_refund", "UPI refund %s to %s" % (money(ev["amount"]), vpa), "normal", "chat")
        return {"paid": True, "amount_inr": ev["amount"], "mode": field(res, "mode", "upi"), "fee_inr": field(res, "fee", UPI_FEE_INR)}

    def prompt_hint(self, ctx):
        return ("For a COD refund ask for the UPI id, call cod_refund_check first, and call cod_refund_payout only if it "
                "says allowed and not needs_human. Tell the customer the UPI fee of Rs %d is deducted." % UPI_FEE_INR)
