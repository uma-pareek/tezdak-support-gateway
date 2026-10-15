"""Legacy (v1) policy, the 2025 handbook values.

Refund window 5 days, human approval above Rs 2000, goodwill once per customer, COD refunds
are never automatic. Kept importable because the loader still accepts `v1` and two support
macros reference it.
"""

from .base import PolicyBase, _get

REFUND_WINDOW_DAYS = 5
APPROVAL_LIMIT_INR = 2000
GOODWILL_AMOUNT_INR = 100


class PolicyV1(PolicyBase):
    name = "v1"
    goodwill_per_customer_once = True

    def __init__(self, window_days=REFUND_WINDOW_DAYS, limit_inr=APPROVAL_LIMIT_INR):
        self._window = window_days
        self._limit = limit_inr

    def window_days(self, shipment, claim=None) -> int:
        return self._window

    def limit_inr(self, shipment, claim=None) -> int:
        return self._limit

    def cod_refund_manual_only(self, shipment=None) -> bool:
        return True

    def goodwill_cap_inr(self, shipment=None):
        return GOODWILL_AMOUNT_INR

    def describe(self) -> dict:
        d = super().describe()
        d.update(window_days=self._window, limit_inr=self._limit, goodwill="once per customer", cod="manual only")
        return d


def is_cod(shipment) -> bool:
    return str(_get(shipment, "payment_mode", "")).upper() == "COD"
