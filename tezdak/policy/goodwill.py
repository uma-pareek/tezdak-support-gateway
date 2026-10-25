"""Goodwill credit rules, evaluated against a policy generation.

history is a list of dicts {"amount_inr": int, "days_ago": int}; callers that have a real
customer store turn `goodwill_history` rows into that shape first.
"""

from dataclasses import dataclass


@dataclass
class GoodwillDecision:
    allowed: bool
    reason: str
    max_amount_inr: int


def goodwill_allowed(policy, requested_inr, history=None, shipment=None) -> GoodwillDecision:
    history = history or []
    cap = policy.goodwill_cap_inr(shipment)
    requested_inr = int(requested_inr)
    if requested_inr <= 0:
        return GoodwillDecision(False, "amount_not_positive", 0)

    if policy.goodwill_per_customer_once and history:
        return GoodwillDecision(False, "already_received_once", 0)

    rolling_cap = policy.goodwill_rolling_cap_inr()
    if rolling_cap is not None:
        days = policy.goodwill_rolling_days()
        used = sum(int(h["amount_inr"]) for h in history if h.get("days_ago", 0) <= days)
        room = max(rolling_cap - used, 0)
        if room == 0:
            return GoodwillDecision(False, "rolling_cap_reached", 0)
        if requested_inr > room:
            return GoodwillDecision(False, "exceeds_rolling_cap", room)
        return GoodwillDecision(True, "within_rolling_cap", room)

    if cap is not None and requested_inr > cap:
        return GoodwillDecision(False, "exceeds_cap", cap)
    return GoodwillDecision(True, "ok", cap if cap is not None else requested_inr)


def goodwill_needs_human(policy, amount_inr, shipment=None) -> bool:
    return policy.requires_approval(int(amount_inr), shipment)
