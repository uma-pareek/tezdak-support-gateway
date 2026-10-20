"""Ticket SLA checks that honour business hours from settings.

Changelog:
  v1  wall-clock hours only
  v2  business-hours aware (`business_hours` setting, "HH:MM-HH:MM"); wall-clock kept behind `business=False`
"""

from datetime import datetime, timedelta

from .db import from_iso

PRIORITY_FACTOR = {"urgent": 0.25, "high": 0.5, "normal": 1.0, "low": 2.0}


def parse_hours(text: str) -> tuple[int, int]:
    """'09:00-21:00' -> (540, 1260) minutes from midnight."""
    try:
        start, end = text.split("-")
        h1, m1 = start.split(":")
        h2, m2 = end.split(":")
        a, b = int(h1) * 60 + int(m1), int(h2) * 60 + int(m2)
    except ValueError as exc:
        raise ValueError(f"bad business_hours {text!r}") from exc
    if not 0 <= a < b <= 24 * 60:
        raise ValueError(f"bad business_hours {text!r}")
    return a, b


def business_minutes_between(start: datetime, end: datetime, window: tuple[int, int]) -> int:
    """Minutes of [start, end) that fall inside the daily window. Walks day by day."""
    if end <= start:
        return 0
    total, day = 0, start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day < end:
        open_at, close_at = day + timedelta(minutes=window[0]), day + timedelta(minutes=window[1])
        lo, hi = max(open_at, start), min(close_at, end)
        if hi > lo:
            total += int((hi - lo).total_seconds() // 60)
        day += timedelta(days=1)
    return total


def sla_hours_for(ticket: dict, base_hours: int) -> float:
    return base_hours * PRIORITY_FACTOR.get(ticket.get("priority", "normal"), 1.0)


def is_breached(ticket: dict, now: datetime, settings, business: bool = True) -> bool:
    if ticket["status"] not in ("open", "pending"):
        return False
    limit = sla_hours_for(ticket, settings.get("ticket_sla_hours", 48))
    updated = from_iso(ticket["updated_at"])
    if business:
        used = business_minutes_between(updated, now, parse_hours(settings.get("business_hours", "09:00-21:00")))
    else:
        used = (now - updated).total_seconds() / 60
    return used > limit * 60


def breached_tickets(store, now: datetime, settings, business: bool = True) -> list[dict]:
    return [t for t in store.list() if is_breached(t, now, settings, business)]
