"""Shared policy interface.

Changelog:
- 2026-03: split out of v1_legacy so v2 could subclass without importing v1.
- 2026-08: added `goodwill_*` hooks, v3 needs them.
"""

from dataclasses import dataclass, field


@dataclass
class Decision:
    allowed: bool
    reason: str
    window_days: int
    limit_inr: int
    needs_human: bool = False
    notes: list = field(default_factory=list)


def _get(obj, key, default=None):
    """Read a key from a dict or an attribute from an object."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class PolicyBase:
    """Every generation answers the same four questions."""

    name = "base"
    max_attempts = 3
    goodwill_per_customer_once = False

    def window_days(self, shipment, claim=None) -> int:
        raise NotImplementedError

    def limit_inr(self, shipment, claim=None) -> int:
        raise NotImplementedError

    def cod_refund_manual_only(self, shipment=None) -> bool:
        return False

    def goodwill_cap_inr(self, shipment=None) -> int | None:
        """Max goodwill amount per grant, None means no explicit cap."""
        return None

    def goodwill_rolling_cap_inr(self) -> int | None:
        """Max total goodwill inside the rolling window, None means no rolling cap."""
        return None

    def goodwill_rolling_days(self) -> int:
        return 30

    def hub_override(self, shipment, claim=None) -> bool:
        return False

    def describe(self) -> dict:
        return {"name": self.name, "max_attempts": self.max_attempts}

    def requires_approval(self, amount_inr, shipment=None, claim=None) -> bool:
        return amount_inr > self.limit_inr(shipment, claim)
