"""Order cancellation with seller rules and cancellable states.

Changelog
  0.3  Per-seller overrides (some sellers never allow post-dispatch cancels).
  0.2  Category rules: perishables cannot be cancelled once picked up.
  0.1  State check only.
"""

from .base import Feature
from .util import AWB_PROP, err, field, missing_args, pick, resolve_awb, safe_call, tool_spec, ticket_id_of

CANCELLABLE = ("IN_TRANSIT",)
CANCEL_AFTER_PICKUP_BLOCKED_CATEGORIES = ("grocery", "perishable")
SELLER_NO_CANCEL = ("QuickKart Foods", "FreshBox")
SELLER_NOTES = {"QuickKart Foods": "Seller does not accept cancellations after dispatch."}
LEGACY_ALLOW_NDR_CANCEL = False  # kept for the old rule set; NDR parcels now go to return flow


def cancel_decision(shipment, order):
    status = field(shipment, "status")
    seller = field(order, "seller", "")
    category = (field(order, "category", "") or "").lower()
    if status == "DELIVERED":
        return False, "already_delivered"
    if status == "RTO_INITIATED":
        return False, "already_returning"
    if seller in SELLER_NO_CANCEL:
        return False, "seller_blocks_cancel"
    if status == "NDR" and LEGACY_ALLOW_NDR_CANCEL:
        return True, "ok_legacy"
    if status in CANCELLABLE:
        if category in CANCEL_AFTER_PICKUP_BLOCKED_CATEGORIES:
            return False, "category_blocked"
        return True, "ok"
    if status in ("OUT_FOR_DELIVERY", "RESCHEDULED", "NDR"):
        return False, "too_late_for_cancel"
    return False, "state_not_cancellable"


REASON_TEXT = {
    "already_delivered": ("This parcel is already delivered, so it cannot be cancelled.",
                          "Parcel deliver ho chuka hai, ab cancel nahi ho sakta."),
    "already_returning": ("This parcel is already going back to the seller.", "Parcel pehle se seller ko wapas ja raha hai."),
    "seller_blocks_cancel": ("This seller does not allow cancellation after dispatch.",
                             "Is seller ke yahan dispatch ke baad cancel nahi hota."),
    "category_blocked": ("This kind of item cannot be cancelled after pickup.",
                         "Is tarah ka item pickup ke baad cancel nahi hota."),
    "too_late_for_cancel": ("The parcel is too close to delivery to cancel. You can refuse it at the door.",
                            "Parcel delivery ke bahut paas hai. Aap darwaze par mana kar sakte hain."),
    "state_not_cancellable": ("This parcel cannot be cancelled in its current state.",
                              "Abhi is state mein cancel nahi ho sakta."),
}


class CancelOrderFeature(Feature):
    name = "cancel_order"
    intents = ("cancel_order",)

    def tool_specs(self):
        return [
            tool_spec("check_cancellable", "Check whether an order can be cancelled.", {"awb": AWB_PROP}, ["awb"]),
            tool_spec("cancel_customer_order", "Cancel an order that is still cancellable and log a ticket.",
                      {"awb": AWB_PROP, "reason": {"type": "string"}}, ["awb", "reason"]),
        ]

    def _load(self, awb, ctx):
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return None, None, e
        if not shipment or field(shipment, "error"):
            return None, None, err("shipment_not_found", awb=awb)
        order = ctx.backend.orders.get(awb)
        if not order:
            return None, None, err("order_not_found", awb=awb)
        return shipment, order, None

    def run_tool(self, name, args, ctx):
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        if name not in ("check_cancellable", "cancel_customer_order"):
            return err("unknown_tool", name=name)
        shipment, order, e = self._load(awb, ctx)
        if e:
            return e
        ok, why = cancel_decision(shipment, order)
        en, hi = REASON_TEXT.get(why, ("", ""))
        message = pick(ctx, en, hi)
        if name == "check_cancellable":
            return {"cancellable": ok, "reason": why, "message": message, "seller_note": SELLER_NOTES.get(field(order, "seller"))}
        miss = missing_args(["reason"], args)
        if miss:
            return err("bad_arguments", missing=miss)
        if not ok:
            return {"cancelled": False, "reason": why, "message": message}
        _, e = safe_call(ctx.backend.orders.cancel, awb, "chat_agent")
        if e:
            return e
        tid, e = safe_call(ctx.backend.tickets.create, awb, "cancel_order",
                           "Cancelled in chat: %s" % args["reason"][:120], "normal", "chat")
        return {"cancelled": True, "awb": awb, "ticket_id": None if e else ticket_id_of(tid)}

    def prompt_hint(self, ctx):
        return ("Ask why they want to cancel, call check_cancellable, and only call cancel_customer_order when it says yes. "
                "If it says no, explain the reason from the tool in one sentence and offer a human follow-up.")
