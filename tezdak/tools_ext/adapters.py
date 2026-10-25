"""Bind the extra tools to a Backend-like object (duck typed).

Expected attributes: `orders` (get, update_address, cancel), `tickets` (create, add_note),
`customers` (get_by_phone), `events` (optional, `publish(topic, payload)`).
"""

import dataclasses


def to_plain(obj):
    """Best-effort conversion of store rows to JSON-able data."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_plain(v) for v in obj]
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return to_plain(dataclasses.asdict(obj))
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dict__"):
        return to_plain({k: v for k, v in vars(obj).items() if not k.startswith("_")})
    return str(obj)


class BackendAdapter:
    def __init__(self, backend, actor="agent"):
        self.backend = backend
        self.actor = actor

    def get_order(self, args):
        row = self.backend.orders.get(args["awb"])
        if row is None:
            return {"error": "ORDER_NOT_FOUND", "awb": args["awb"]}
        return {"order": to_plain(row)}

    def update_address(self, args):
        if self.backend.orders.get(args["awb"]) is None:
            return {"error": "ORDER_NOT_FOUND", "awb": args["awb"]}
        self.backend.orders.update_address(args["awb"], args["new_address"], args.get("by", self.actor))
        return {"ok": True, "awb": args["awb"]}

    def cancel_order(self, args):
        if self.backend.orders.get(args["awb"]) is None:
            return {"error": "ORDER_NOT_FOUND", "awb": args["awb"]}
        self.backend.orders.cancel(args["awb"], args.get("by", self.actor))
        return {"ok": True, "awb": args["awb"]}

    def create_ticket(self, args):
        ticket_id = self.backend.tickets.create(
            args["awb"], args["kind"], args["summary"], priority=args.get("priority", "normal"), source="chat")
        return {"ticket_id": ticket_id}

    def get_customer(self, args):
        row = self.backend.customers.get_by_phone(args["phone"])
        if row is None:
            return {"error": "CUSTOMER_NOT_FOUND"}
        return {"customer": to_plain(row)}

    def add_ticket_note(self, args):
        self.backend.tickets.add_note(args["ticket_id"], args["text"], args.get("author", self.actor))
        return {"ok": True, "ticket_id": args["ticket_id"]}

    def send_template_message(self, args):
        events = getattr(self.backend, "events", None)
        if events is None or not hasattr(events, "publish"):
            return {"error": "MESSAGING_UNAVAILABLE"}
        payload = {"phone": args["phone"], "template": args["template"], "params": args.get("params", [])}
        events.publish("template_message", payload)
        return {"queued": True, "template": args["template"]}


def build_handlers(backend, actor="agent"):
    """Map tool name -> callable(args) for every tool this adapter implements."""
    adapter = BackendAdapter(backend, actor)
    names = ["get_order", "update_address", "cancel_order", "create_ticket",
             "get_customer", "add_ticket_note", "send_template_message"]
    return {n: getattr(adapter, n) for n in names}
