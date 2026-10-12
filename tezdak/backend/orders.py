"""Order records with address history and cancellation."""

import json


class OrderError(ValueError):
    pass


class OrderStore:
    def __init__(self, db, events=None):
        self.db = db
        self.events = events

    def put(self, awb: str, seller: str, category: str, items: list, value_inr: int,
            address_text: str, phone: str) -> dict:
        if not awb:
            raise OrderError("awb required")
        self.db.execute(
            "INSERT OR REPLACE INTO orders(awb, seller, category, items_json, value_inr, address_text, phone, "
            "cancelled, cancelled_by) VALUES (?,?,?,?,?,?,?,COALESCE((SELECT cancelled FROM orders WHERE awb = ?),0),"
            "(SELECT cancelled_by FROM orders WHERE awb = ?))",
            (awb, seller, category, json.dumps(items), int(value_inr), address_text, phone, awb, awb),
        )
        return self.get(awb)

    def get(self, awb: str) -> dict | None:
        row = self.db.query_one("SELECT * FROM orders WHERE awb = ?", (awb,))
        if row is None:
            return None
        row["items"] = json.loads(row.pop("items_json"))
        row["cancelled"] = bool(row["cancelled"])
        return row

    def update_address(self, awb: str, new_text: str, by: str) -> dict:
        order = self.get(awb)
        if order is None:
            raise OrderError(f"order {awb} not found")
        if order["cancelled"]:
            raise OrderError(f"order {awb} is cancelled")
        if not new_text or not new_text.strip():
            raise OrderError("address cannot be empty")
        self.db.execute(
            "INSERT INTO address_history(awb, old_text, new_text, by, ts) VALUES (?,?,?,?,?)",
            (awb, order["address_text"], new_text, by, self.db.now_iso()),
        )
        self.db.execute("UPDATE orders SET address_text = ? WHERE awb = ?", (new_text, awb))
        if self.events is not None:
            self.events.publish("order.address_updated", {"awb": awb, "by": by})
        return self.get(awb)

    def cancel(self, awb: str, by: str) -> dict:
        order = self.get(awb)
        if order is None:
            raise OrderError(f"order {awb} not found")
        if order["cancelled"]:
            return order
        self.db.execute("UPDATE orders SET cancelled = 1, cancelled_by = ? WHERE awb = ?", (by, awb))
        if self.events is not None:
            self.events.publish("order.cancelled", {"awb": awb, "by": by})
        return self.get(awb)

    def address_history(self, awb: str) -> list[dict]:
        return self.db.query("SELECT old_text, new_text, by, ts FROM address_history WHERE awb = ? ORDER BY id", (awb,))

    def by_phone(self, phone: str) -> list[dict]:
        rows = self.db.query("SELECT awb FROM orders WHERE phone = ? ORDER BY awb", (phone,))
        return [self.get(r["awb"]) for r in rows]

    def by_seller(self, seller: str) -> list[dict]:
        rows = self.db.query("SELECT awb FROM orders WHERE seller = ? ORDER BY awb", (seller,))
        return [self.get(r["awb"]) for r in rows]
