"""Small in-memory carrier used by the agent tests."""

import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tezdak.carrier_client import CarrierTimeout  # noqa: E402

IST = timezone(timedelta(hours=5, minutes=30))


def raw_scans():
    return [
        {"ts": "2026-11-02T09:00:00+05:30", "status": "OFD", "status_text": "Out for delivery", "hub_id": "LKO-1",
         "ofd_ts": "2026-11-02T09:00:00+05:30", "attempt_n": 1, "otp_verified": False},
        {"ts": "2026-11-02T09:06:00+05:30", "status": "NDR", "status_text": "Customer not available",
         "hub_id": "LKO-1", "ofd_ts": "2026-11-02T09:00:00+05:30", "attempt_n": 1, "otp_verified": False,
         "ev": {"loc": {"lat": 26.9, "lng": 80.9}, "cl": {"attempted": False, "dur_s": 0}}},
    ]


class FakeCarrier:
    def __init__(self, status="OUT_FOR_DELIVERY", attempts_used=1, slow=False, timeouts_on_reads=0):
        self.now = datetime(2026, 11, 2, 12, 10, tzinfo=IST)
        self.shipment = {"awb": "TZ4829301", "status": status, "attempts_used": attempts_used,
                         "payment_mode": "COD", "amount_inr": 1499, "pincode": "226016", "tier": "tier2",
                         "phone": "+91-90000-00001", "otp_required": False}
        self.slow = slow
        self.read_timeouts_left = timeouts_on_reads
        self.log = []

    def _record(self, name, **kw):
        self.log.append((name, kw))

    def names(self):
        return [n for n, _ in self.log]

    def get_shipment(self, awb, timeout_s=8.0):
        self._record("get_shipment", awb=awb)
        if self.read_timeouts_left > 0:
            self.read_timeouts_left -= 1
            raise CarrierTimeout("read timed out")
        return dict(self.shipment)

    def get_scans(self, awb, timeout_s=8.0):
        self._record("get_scans", awb=awb)
        return raw_scans()

    def reschedule(self, awb, slot, client_ref=None, timeout_s=8.0):
        self._record("reschedule", awb=awb, slot=slot, client_ref=client_ref)
        self.shipment["attempts_used"] += 1
        self.shipment["status"] = "RESCHEDULED"
        if self.slow and 9.0 > timeout_s:
            raise CarrierTimeout("write timed out")
        return {"status": "RESCHEDULED", "slot_booked": self.now.date().isoformat() if slot == "today"
                else (self.now.date() + timedelta(days=1)).isoformat() if slot == "tomorrow" else slot}

    def open_rider_dispute(self, awb, reason, timeout_s=8.0):
        self._record("open_rider_dispute", awb=awb)
        return {"ticket_id": "D-1"}

    def create_refund(self, awb, amount_inr, kind, vpa=None, timeout_s=8.0):
        self._record("create_refund", awb=awb, amount_inr=amount_inr)
        return {"mode": "wallet", "fee": 0}

    def escalate(self, awb, reason, kind, timeout_s=8.0):
        self._record("escalate", awb=awb, kind=kind)
        return {"ticket_id": "E-1"}

    def close(self, awb, resolution):
        self._record("close", awb=awb)
        return {"closed": True}
