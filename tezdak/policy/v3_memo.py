"""Policy v3, from the September ops memo (limits per category, windows per payment mode).

Limits: electronics 3000, apparel 1500, grocery 800, other 2000.
Window: 10 days prepaid, 7 days COD.
Goodwill: capped at Rs 100 per customer per rolling 30 days.
Hub override: from attempt 3 the hub manager may approve a refund outside the window.

Not the default yet. TODO confirm with finance whether the hub override also lifts the limit.
"""

from .base import PolicyBase, _get

CATEGORY_LIMITS_INR = {"electronics": 3000, "apparel": 1500, "grocery": 800}
OTHER_LIMIT_INR = 2000
WINDOW_PREPAID_DAYS = 10
WINDOW_COD_DAYS = 7
GOODWILL_ROLLING_CAP_INR = 100
GOODWILL_ROLLING_DAYS = 30
HUB_OVERRIDE_ATTEMPT = 3


class PolicyV3(PolicyBase):
    name = "v3"

    def __init__(self, hub_override_enabled=True):
        self.hub_override_enabled = hub_override_enabled

    def window_days(self, shipment, claim=None) -> int:
        mode = str(_get(shipment, "payment_mode", "PREPAID")).upper()
        return WINDOW_COD_DAYS if mode == "COD" else WINDOW_PREPAID_DAYS

    def limit_inr(self, shipment, claim=None) -> int:
        category = _get(claim, "category") or _get(shipment, "category")
        return CATEGORY_LIMITS_INR.get(category, OTHER_LIMIT_INR)

    def goodwill_cap_inr(self, shipment=None):
        return GOODWILL_ROLLING_CAP_INR

    def goodwill_rolling_cap_inr(self):
        return GOODWILL_ROLLING_CAP_INR

    def goodwill_rolling_days(self) -> int:
        return GOODWILL_ROLLING_DAYS

    def hub_override(self, shipment, claim=None) -> bool:
        if not self.hub_override_enabled:
            return False
        return int(_get(shipment, "attempts_used", 0) or 0) >= HUB_OVERRIDE_ATTEMPT

    def describe(self) -> dict:
        d = super().describe()
        d.update(limits=dict(CATEGORY_LIMITS_INR, other=OTHER_LIMIT_INR),
                 window_prepaid=WINDOW_PREPAID_DAYS, window_cod=WINDOW_COD_DAYS,
                 goodwill_cap=GOODWILL_ROLLING_CAP_INR, hub_override_attempt=HUB_OVERRIDE_ATTEMPT)
        return d
