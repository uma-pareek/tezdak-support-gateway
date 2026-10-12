"""CSV and JSON dumps of the stores, for the ops team and for debugging."""

import csv
import io
import json

TICKET_COLUMNS = ("id", "awb", "kind", "status", "priority", "source", "reopen_count", "note_count",
                  "created_at", "updated_at")
ORDER_COLUMNS = ("awb", "seller", "category", "value_inr", "cancelled", "phone")


def rows_to_csv(rows: list[dict], columns: tuple) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(columns), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buf.getvalue()


def tickets_csv(backend) -> str:
    return rows_to_csv(backend.tickets.export_rows(), TICKET_COLUMNS)


def orders_csv(backend) -> str:
    rows = backend.db.query("SELECT awb FROM orders ORDER BY awb")
    return rows_to_csv([backend.orders.get(r["awb"]) for r in rows], ORDER_COLUMNS)


def dump_json(backend) -> str:
    """Whole-backend dump. Goodwill rows keep the phone because the ledger is keyed by it."""
    data = {
        "tickets": backend.tickets.export_rows(),
        "orders": [backend.orders.get(r["awb"]) for r in backend.db.query("SELECT awb FROM orders ORDER BY awb")],
        "customers": backend.db.query("SELECT * FROM customers ORDER BY phone"),
        "goodwill": backend.db.query("SELECT * FROM goodwill ORDER BY id"),
        "audit": backend.audit.entries(),
    }
    return json.dumps(data, indent=2, sort_keys=True, default=str)


def redact_phone(phone: str) -> str:
    return phone[:-8] + "XXXX" + phone[-4:] if len(phone) > 8 else "XXXX"
