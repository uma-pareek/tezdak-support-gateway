"""`Backend` bundles every store behind one object so features take a single argument."""

from dataclasses import dataclass

from .customers import CustomerStore
from .db import Db
from .events import AuditLog, EventBus
from .flags import FlagService
from .orders import OrderStore
from .seed import scenario_now, seed_from_scenario
from .settings import Settings
from .tickets import TicketStore


@dataclass
class Backend:
    db: Db
    tickets: TicketStore
    customers: CustomerStore
    orders: OrderStore
    events: EventBus
    audit: AuditLog
    flags: FlagService
    settings: Settings

    @classmethod
    def in_memory(cls, clock=None, flags: dict | None = None, settings: dict | None = None,
                  environ=None) -> "Backend":
        db = Db(":memory:", clock=clock)
        events = EventBus()
        audit = AuditLog(db)
        audit.attach(events)
        return cls(
            db=db,
            tickets=TicketStore(db, events),
            customers=CustomerStore(db),
            orders=OrderStore(db, events),
            events=events,
            audit=audit,
            flags=FlagService(flags, environ=environ if environ is not None else {}),
            settings=Settings(overrides=settings, environ=environ if environ is not None else {}),
        )

    @classmethod
    def from_scenario(cls, scenario: dict, **kwargs) -> "Backend":
        backend = cls.in_memory(**kwargs)
        start = scenario_now(scenario)
        if start is not None and "clock" not in kwargs:
            backend.db.set_clock(lambda: start)
        seed_from_scenario(backend, scenario)
        backend.seeded_awb = scenario["world"]["shipment"]["awb"]
        return backend

    @classmethod
    def from_world(cls, path: str | None = None, scenario: dict | None = None, **kwargs) -> "Backend":
        from .world import open_world
        return open_world(cls, path, scenario, **kwargs)

    def close(self) -> None:
        self.db.close()

    def snapshot(self) -> dict:
        """Row counts for quick health checks and tests."""
        return {
            "schema_version": self.db.schema_version(),
            "tickets": len(self.tickets.list()),
            "customers": self.customers.count(),
            "orders": self.db.query_one("SELECT COUNT(*) AS n FROM orders")["n"],
            "audit_entries": self.audit.count(),
            "active_flags": len(self.flags.active()),
        }
