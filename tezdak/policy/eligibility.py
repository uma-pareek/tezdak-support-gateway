"""Refund eligibility for a delivered or failed shipment.

`refund_eligibility(shipment, claim, policy)` is policy-generation agnostic: it asks the
policy for window, limit and special rules and builds a Decision.

claim keys used: amount_inr, days_since_delivery, category, seller, kind.
"""

from .base import Decision, _get

REFUNDABLE_STATUSES = {"DELIVERED", "NDR", "RTO", "RTO_INITIATED", "LOST", "DAMAGED"}


def _days_since_delivery(shipment, claim):
    days = _get(claim, "days_since_delivery")
    if days is None:
        days = _get(shipment, "days_since_delivery")
    return days


def refund_eligibility(shipment, claim, policy) -> Decision:
    window = policy.window_days(shipment, claim)
    limit = policy.limit_inr(shipment, claim)
    amount = _get(claim, "amount_inr")
    if amount is None:
        amount = _get(shipment, "amount_inr", 0)
    amount = int(amount or 0)
    status = str(_get(shipment, "status", "")).upper()
    notes = []

    def decide(allowed, reason, needs_human=False):
        return Decision(allowed, reason, window, limit, needs_human, notes)

    if amount <= 0:
        return decide(False, "amount_not_positive")
    if status not in REFUNDABLE_STATUSES:
        return decide(False, "status_not_refundable")

    days = _days_since_delivery(shipment, claim)
    outside = days is not None and days > window
    if outside:
        if policy.hub_override(shipment, claim):
            notes.append("hub_override")
            return decide(True, "outside_window_hub_override", needs_human=True)
        return decide(False, "outside_window")

    is_cod = str(_get(shipment, "payment_mode", "")).upper() == "COD"
    if is_cod and policy.cod_refund_manual_only(shipment):
        notes.append("cod_manual")
        return decide(True, "cod_manual_only", needs_human=True)

    if amount > limit:
        return decide(True, "above_limit", needs_human=True)
    return decide(True, "within_policy")
