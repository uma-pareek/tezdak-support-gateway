"""Thin client over the carrier API (the simulator in this repo)."""

from datetime import datetime, timedelta, timezone

try:  # the simulator ships as a vendor module
    from carrier_sim import CarrierSim, CarrierTimeout
except ImportError:  # pragma: no cover - exercised only without the vendor module
    CarrierSim = None

    class CarrierTimeout(Exception):
        pass

CARRIER_TIMEOUT_S = 8.0
IST = timezone(timedelta(hours=5, minutes=30))


class CarrierClient:
    """Wraps a carrier object (CarrierSim or anything with the same methods)."""

    def __init__(self, sim):
        self._sim = sim

    @classmethod
    def from_scenario(cls, scenario: dict) -> "CarrierClient":
        if CarrierSim is None:
            raise RuntimeError("carrier_sim is not importable; set PYTHONPATH to the vendor folder")
        return cls(CarrierSim(scenario))

    @property
    def sim(self):
        return self._sim

    @property
    def now(self) -> datetime:
        return getattr(self._sim, "now", None) or datetime.now(IST)

    def get_shipment(self, awb, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.get_shipment(awb, timeout_s=timeout_s)

    def get_scans(self, awb, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.get_scans(awb, timeout_s=timeout_s)

    def reschedule(self, awb, slot, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.reschedule(awb, slot, timeout_s=timeout_s)

    def open_rider_dispute(self, awb, reason, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.open_rider_dispute(awb, reason, timeout_s=timeout_s)

    def create_refund(self, awb, amount_inr, kind, vpa=None, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.create_refund(awb, amount_inr, kind, vpa=vpa, timeout_s=timeout_s)

    def escalate(self, awb, reason, kind, timeout_s=CARRIER_TIMEOUT_S):
        return self._sim.escalate(awb, reason, kind, timeout_s=timeout_s)

    def close(self, awb, resolution, timeout_s=None):
        return self._sim.close(awb, resolution)

    def ledger(self):
        return self._sim.ledger()

    def outcome(self):
        return self._sim.outcome()
