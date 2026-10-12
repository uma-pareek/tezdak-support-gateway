"""Change the delivery address before the parcel goes out.

Flow: customer gives the new address text -> we check the order exists and the
parcel is not out for delivery -> update through the order store -> open a
ticket so the hub can see the change.

Changelog
  0.3  Pincode must match the original pincode (cross-city moves go to a human).
  0.2  Ticket created on every successful change.
  0.1  Text-only update.
"""

import re

from .base import Feature
from .util import (AWB_PROP, err, field, list_tickets, missing_args, pick, resolve_awb, safe_call, ticket_id_of,
                   tool_spec)

LOCKED_STATUSES = ("OUT_FOR_DELIVERY", "DELIVERED", "RTO_INITIATED")
MIN_ADDRESS_CHARS = 15
MAX_CHANGES = 2
PIN_RE = re.compile(r"\b(\d{6})\b")
ALLOW_PINCODE_CHANGE = False  # flag: leave off, hub routing depends on the pincode


def validate_address(text):
    t = " ".join((text or "").split())
    if len(t) < MIN_ADDRESS_CHARS:
        return None, "address_too_short"
    if not re.search(r"\d", t):
        return None, "address_needs_house_or_pin"
    return t, None


def pincode_in(text):
    m = PIN_RE.search(text or "")
    return m.group(1) if m else None


class AddressUpdateFeature(Feature):
    name = "address_update"
    intents = ("address_change",)

    def tool_specs(self):
        return [
            tool_spec("check_address_change", "Check whether the delivery address of this order can still be changed.",
                      {"awb": AWB_PROP}, ["awb"]),
            tool_spec("update_delivery_address", "Replace the delivery address of an order that has not gone out for delivery.",
                      {"awb": AWB_PROP, "new_address": {"type": "string", "description": "Full new address with pincode"}},
                      ["awb", "new_address"]),
        ]

    def _eligibility(self, awb, ctx):
        shipment, e = safe_call(ctx.carrier.get_shipment, awb)
        if e:
            return None, e
        if not shipment or field(shipment, "error"):
            return None, err("shipment_not_found", awb=awb)
        status = field(shipment, "status")
        if status in LOCKED_STATUSES:
            return None, err("address_locked", status=status,
                             message="Parcel is already out for delivery or finished; address cannot change.")
        order = ctx.backend.orders.get(awb)
        if not order:
            return None, err("order_not_found", awb=awb)
        history = list(ctx.backend.orders.address_history(awb) or [])
        if len(history) >= MAX_CHANGES:
            return None, err("too_many_changes", changes=len(history))
        return {"shipment": shipment, "order": order, "changes": len(history)}, None

    def run_tool(self, name, args, ctx):
        awb = resolve_awb(ctx, args)
        if not awb:
            return err("awb_required")
        if name == "check_address_change":
            elig, e = self._eligibility(awb, ctx)
            if e:
                return dict(e, can_change=False)
            return {"can_change": True, "awb": awb, "changes_so_far": elig["changes"]}
        if name != "update_delivery_address":
            return err("unknown_tool", name=name)
        miss = missing_args(["new_address"], args)
        if miss:
            return err("bad_arguments", missing=miss)
        text, why = validate_address(args["new_address"])
        if why:
            return err(why)
        elig, e = self._eligibility(awb, ctx)
        if e:
            return e
        old_pin = pincode_in(field(elig["order"], "address_text", ""))
        new_pin = pincode_in(text)
        if not ALLOW_PINCODE_CHANGE and old_pin and new_pin and old_pin != new_pin:
            return err("pincode_change_needs_human", old_pincode=old_pin, new_pincode=new_pin)
        _, e = safe_call(ctx.backend.orders.update_address, awb, text, "chat_agent")
        if e:
            return e
        tid, e = safe_call(ctx.backend.tickets.create, awb, "address_change",
                           "Address changed in chat: %s" % text[:120], "normal", "chat")
        out = {"updated": True, "awb": awb, "new_address": text}
        if e:
            out["ticket_error"] = e["detail"]
        else:
            out["ticket_id"] = ticket_id_of(tid)
        return out

    def prompt_hint(self, ctx):
        base = ("Ask for the full new address including pincode. Call check_address_change first, "
                "then update_delivery_address. Never change an address for a parcel that is out for delivery.")
        return base + pick(ctx, "", " Hinglish mein poochho: 'Naya address pincode ke saath bhej dijiye.'")

    def open_changes(self, awb, backend):
        return [t for t in list_tickets(backend, awb=awb) if field(t, "kind") == "address_change"]
