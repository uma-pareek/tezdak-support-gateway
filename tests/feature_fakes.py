"""In-memory stand-ins for the backend and carrier used by the feature tests.

Method names follow the backend contract (tickets, customers, orders, events).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tezdak.carrier_client import CarrierTimeout  # noqa: E402
from tezdak.features.base import FeatureContext  # noqa: E402
from tezdak.policies import Policies  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 2, 9, 30, tzinfo=IST)
AWB = "TZ4829301"


class FakeTickets:
    def __init__(self):
        self.rows = {}
        self.next_id = 1
        self.fail_create = False

    def create(self, awb, kind, summary, priority="normal", source="chat"):
        if self.fail_create:
            raise RuntimeError("ticket store down")
        tid = self.next_id
        self.next_id += 1
        self.rows[tid] = {"id": tid, "awb": awb, "kind": kind, "summary": summary, "priority": priority,
                          "source": source, "status": "open", "notes": [], "audit": [("created", NOW.isoformat())]}
        return tid

    def get(self, id):
        return self.rows.get(id)

    def list(self, status=None, awb=None):
        return [dict(r) for r in self.rows.values()
                if (status is None or r["status"] == status) and (awb is None or r["awb"] == awb)]

    def add_note(self, id, text, author):
        self.rows[id]["notes"].append({"text": text, "author": author})

    def set_status(self, id, status):
        self.rows[id]["status"] = status

    def reopen(self, id, reason):
        self.rows[id]["status"] = "open"
        self.rows[id]["audit"].append(("reopened", reason))


class FakeCustomers:
    def __init__(self):
        self.rows = {}
        self.goodwill = []

    def upsert(self, phone, name, language):
        self.rows[phone] = {"phone": phone, "name": name, "language": language}

    def get_by_phone(self, phone):
        return self.rows.get(phone)

    def record_goodwill(self, phone, amount_inr, ts):
        self.goodwill.append((phone, amount_inr, ts))

    def goodwill_history(self, phone, days, now):
        return [g for g in self.goodwill if g[0] == phone]


class FakeOrders:
    def __init__(self):
        self.rows = {}
        self.history = {}

    def put(self, awb, seller, category, items, value_inr, address_text, phone):
        self.rows[awb] = {"awb": awb, "seller": seller, "category": category, "items": items, "value_inr": value_inr,
                          "address_text": address_text, "phone": phone, "status": "active"}

    def get(self, awb):
        return self.rows.get(awb)

    def update_address(self, awb, new_text, by):
        self.history.setdefault(awb, []).append({"old": self.rows[awb]["address_text"], "new": new_text, "by": by})
        self.rows[awb]["address_text"] = new_text

    def cancel(self, awb, by):
        self.rows[awb]["status"] = "cancelled"

    def address_history(self, awb):
        return list(self.history.get(awb, []))


class FakeEvents:
    def __init__(self):
        self.items = []

    def publish(self, *a, **kw):
        self.items.append((a, kw))


class FakeBackend:
    def __init__(self):
        self.tickets = FakeTickets()
        self.customers = FakeCustomers()
        self.orders = FakeOrders()
        self.events = FakeEvents()
        self.orders.put(AWB, "Nova Apparel", "apparel", ["kurta"], 1499, "12 Rose Lane, Gomti Nagar, Lucknow 226016",
                        "+91-90000-00001")


def make_scans(status, now=NOW, delivered_days_ago=1):
    base = [{"ts": (now - timedelta(days=2)).isoformat(), "status": "IN_TRANSIT", "status_text": "Arrived at hub",
             "hub_id": "H1", "ofd_ts": None, "attempt_n": 0, "otp_verified": False}]
    if status == "DELIVERED":
        d = now - timedelta(days=delivered_days_ago)
        base.append({"ts": d.isoformat(), "status": "DELIVERED", "status_text": "Delivered", "hub_id": "H1",
                     "ofd_ts": d.isoformat(), "attempt_n": 1, "otp_verified": False})
    elif status in ("OUT_FOR_DELIVERY", "NDR", "RESCHEDULED"):
        base.append({"ts": (now - timedelta(hours=1)).isoformat(), "status": status, "status_text": status.title(),
                     "hub_id": "H1", "ofd_ts": None, "attempt_n": 1, "otp_verified": False})
    return base


class FeatureCarrier:
    def __init__(self, status="IN_TRANSIT", payment_mode="COD", amount_inr=1499, attempts_used=1, tier="tier2",
                 scans=None, now=NOW, otp_required=False, delivered_days_ago=1):
        self.now = now
        self.shipment = {"awb": AWB, "status": status, "attempts_used": attempts_used, "payment_mode": payment_mode,
                         "amount_inr": amount_inr, "pincode": "226016", "tier": tier, "phone": "+91-90000-00001",
                         "otp_required": otp_required}
        self._scans = scans if scans is not None else make_scans(status, now, delivered_days_ago)
        self.calls = []
        self.timeout_next = False

    def names(self):
        return [c[0] for c in self.calls]

    def get_shipment(self, awb, timeout_s=8.0):
        self.calls.append(("get_shipment", awb))
        if awb != AWB:
            return {"error": "NOT_FOUND"}
        return dict(self.shipment)

    def get_scans(self, awb, timeout_s=8.0):
        self.calls.append(("get_scans", awb))
        return [dict(s) for s in self._scans]

    def reschedule(self, awb, slot, client_ref=None, timeout_s=8.0):
        self.calls.append(("reschedule", awb, slot))
        if self.timeout_next:
            raise CarrierTimeout("slow")
        return {"status": "RESCHEDULED", "slot_booked": slot}

    def create_refund(self, awb, amount_inr, kind, vpa=None, timeout_s=8.0):
        self.calls.append(("create_refund", awb, amount_inr, kind, vpa))
        if self.shipment["payment_mode"] == "COD" and not vpa:
            return {"error": "VPA_REQUIRED"}
        return {"mode": "upi", "fee": 6}

    def open_rider_dispute(self, awb, reason, timeout_s=8.0):  # must never be called by features
        self.calls.append(("open_rider_dispute", awb))
        return {"ticket_id": "D-1"}

    def escalate(self, awb, reason, kind, timeout_s=8.0):
        self.calls.append(("escalate", awb))
        return {"ticket_id": "E-1"}


def make_ctx(carrier=None, backend=None, text="", intent="other", language="english", awb=AWB, now=NOW, policies=None):
    return FeatureContext(awb=awb, user_text=text, intent=intent, language=language,
                          carrier=carrier or FeatureCarrier(), backend=backend or FakeBackend(),
                          policies=policies or Policies(), now=now)
