"""Open the shipped background world (`data/tezdak.db`) as a private working copy.

The shipped file is never opened for writing: it is copied to a temp file first, and the temp
copy is removed when the backend is garbage collected or at interpreter exit.
"""

import os
import shutil
import tempfile
import weakref
from datetime import datetime

from .customers import CustomerStore
from .db import IST, Db
from .events import AuditLog, EventBus
from .flags import FlagService
from .orders import OrderStore
from .seed import scenario_now, seed_from_scenario
from .settings import Settings
from .tickets import TicketStore

DEFAULT_PATH = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "tezdak.db"))
WORLD_NOW = datetime(2026, 11, 2, 12, 0, tzinfo=IST)


def _drop(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def open_world(backend_cls, path: str | None = None, scenario: dict | None = None, clock=None, environ=None):
    """Build a `backend_cls` on a temp copy of the world db; seed the scenario rows if given."""
    src = path or DEFAULT_PATH
    if not os.path.isfile(src):
        raise FileNotFoundError(f"world db not found: {src}")
    fd, tmp = tempfile.mkstemp(prefix="tezdak_world_", suffix=".db")
    os.close(fd)
    shutil.copyfile(src, tmp)
    start = (scenario_now(scenario) if scenario else None) or WORLD_NOW
    db = Db(tmp, clock=clock or (lambda: start))
    events = EventBus()
    audit = AuditLog(db)
    audit.attach(events)
    env = environ if environ is not None else {}
    backend = backend_cls(
        db=db,
        tickets=TicketStore(db, events),
        customers=CustomerStore(db),
        orders=OrderStore(db, events),
        events=events,
        audit=audit,
        flags=FlagService(None, environ=env),
        settings=Settings(environ=env),
    )
    backend.world_copy_path = tmp
    weakref.finalize(backend, _drop, tmp)
    if scenario is not None:
        seed_from_scenario(backend, scenario)
        backend.seeded_awb = scenario["world"]["shipment"]["awb"]
    return backend
