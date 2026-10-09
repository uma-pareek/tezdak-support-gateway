"""Create customer and order rows from a scenario's `world.shipment`.

Scenarios come from `data/dev/*.json` or the private scenario generator; both share the same shape.
"""

from datetime import datetime, timedelta

from .db import IST

CATEGORY_BY_TIER = {"metro": "electronics", "tier2": "apparel", "tier3": "grocery"}
SELLERS = ("Kapda Ghar", "GadgetBazaar", "DesiMart", "Urban Stitch")
ITEM_NAMES = {
    "electronics": ["wireless earbuds", "phone cover"],
    "apparel": ["cotton kurta", "denim jacket"],
    "grocery": ["atta 5kg", "cooking oil 1L"],
    "other": ["desk lamp"],
}
ADDRESS_STUB = "Flat {n}, Sector {s}, pincode {pin}"


def _language_of(scenario: dict) -> str:
    card = (scenario.get("customer") or {}).get("card") or {}
    code = card.get("language", "en")
    tags = scenario.get("slice_tags") or []
    if code == "hi" or "hinglish" in tags:
        return "hinglish"
    return "english"


def _stable_index(text: str, size: int) -> int:
    return sum(ord(c) for c in text) % size


def scenario_now(scenario: dict) -> datetime | None:
    raw = (scenario.get("world") or {}).get("now")
    if not raw:
        return None
    dt = datetime.fromisoformat(raw)
    return dt if dt.tzinfo else dt.replace(tzinfo=IST)


def seed_from_scenario(backend, scenario: dict) -> dict:
    """Seed a customer and an order. Returns {"awb","phone","customer","order"}."""
    world = scenario.get("world") or {}
    ship = world.get("shipment")
    if not ship or "awb" not in ship:
        raise ValueError("scenario has no world.shipment.awb")
    awb, phone = ship["awb"], ship.get("phone") or ""
    tier = ship.get("tier", "metro")
    category = CATEGORY_BY_TIER.get(tier, "other")
    seller = SELLERS[_stable_index(awb, len(SELLERS))]
    items = [{"name": n, "qty": 1} for n in ITEM_NAMES[category][:1]]
    address = ADDRESS_STUB.format(n=_stable_index(awb, 90) + 10, s=_stable_index(phone, 40) + 1,
                                  pin=ship.get("pincode", "000000"))
    customer = None
    if phone:
        customer = backend.customers.upsert(phone, None, _language_of(scenario))
        if world.get("prior_goodwill_30d"):
            now = scenario_now(scenario) or backend.db.now()
            backend.customers.record_goodwill(phone, 50, now - timedelta(days=5))
    order = backend.orders.put(awb, seller, category, items, int(ship.get("amount_inr", 0)), address, phone)
    backend.events.publish("seed.scenario", {"awb": awb, "scenario": scenario.get("id")})
    return {"awb": awb, "phone": phone, "customer": customer, "order": order}
