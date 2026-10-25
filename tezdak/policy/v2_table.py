"""Table driven policy (v2).

Values live in tables so ops can change them without a release. Window 7 days, limit Rs 5000.
Categories and seller exceptions override the defaults.

Changelog:
- 2026-04: first table version, defaults only.
- 2026-06: seller exceptions (marketplace sellers with their own return terms).
- 2026-09: `bulk_seller` entry added by support ops, TODO move this table to the backend settings store.
"""

from .base import PolicyBase, _get

DEFAULTS = {"window_days": 7, "limit_inr": 5000}

CATEGORY_TABLE = {
    "electronics": {"window_days": 7, "limit_inr": 5000},
    "apparel": {"window_days": 7, "limit_inr": 5000},
    "grocery": {"window_days": 2, "limit_inr": 5000},
    "books": {"window_days": 7, "limit_inr": 5000},
}

SELLER_EXCEPTIONS = {
    "SELLER-FASHIONKART": {"window_days": 10},
    "SELLER-GADGETHUB": {"limit_inr": 8000},
    "SELLER-BULKMART": {"window_days": 3, "limit_inr": 3000},
}


class PolicyV2(PolicyBase):
    name = "v2"

    def __init__(self, defaults=None, categories=None, sellers=None):
        self.defaults = dict(DEFAULTS if defaults is None else defaults)
        self.categories = dict(CATEGORY_TABLE if categories is None else categories)
        self.sellers = dict(SELLER_EXCEPTIONS if sellers is None else sellers)

    def _lookup(self, key, shipment, claim):
        seller = _get(claim, "seller") or _get(shipment, "seller")
        if seller and key in self.sellers.get(seller, {}):
            return self.sellers[seller][key]
        category = _get(claim, "category") or _get(shipment, "category")
        if category and key in self.categories.get(category, {}):
            return self.categories[category][key]
        return self.defaults[key]

    def window_days(self, shipment, claim=None) -> int:
        return self._lookup("window_days", shipment, claim)

    def limit_inr(self, shipment, claim=None) -> int:
        return self._lookup("limit_inr", shipment, claim)

    def goodwill_cap_inr(self, shipment=None):
        return 200

    def describe(self) -> dict:
        d = super().describe()
        d.update(defaults=dict(self.defaults), categories=sorted(self.categories), sellers=sorted(self.sellers))
        return d
