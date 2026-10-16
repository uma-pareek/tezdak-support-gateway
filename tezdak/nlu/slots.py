"""Slot filling for scheduling-style messages ("kal shaam 6 baje ke baad").

Pure text work: pulls a requested day and window from the entities. It does not decide whether the
slot is allowed; that belongs to the agent and the policies.
"""

from dataclasses import dataclass
from datetime import date, datetime

from .entities import Entities, extract

WINDOWS = {
    "morning": (9, 12), "afternoon": (12, 16), "evening": (16, 20), "night": (20, 22),
}


@dataclass
class SlotRequest:
    day_word: str | None = None       # "today" | "tomorrow" | "date" | None
    day: date | None = None
    window: str | None = None
    earliest_hour: int | None = None
    latest_hour: int | None = None
    complete: bool = False


def _day_word(word: str, day: date, now: datetime | None) -> str:
    if word in ("aaj", "today"):
        return "today"
    if word in ("kal", "tomorrow", "tmrw", "tmr"):
        return "tomorrow"
    return "date"


def fill_slots(text: str, now: datetime | None = None, entities: Entities | None = None) -> SlotRequest:
    ents = entities or extract(text, now)
    req = SlotRequest()
    if ents.dates:
        word, day = ents.dates[0]
        req.day_word, req.day = _day_word(word, day, now), day
    if ents.times_of_day:
        req.window = ents.times_of_day[0]
        req.earliest_hour, req.latest_hour = WINDOWS[req.window]
    low = (text or "").lower()
    if ents.clock_times:
        hour = ents.clock_times[0][0]
        if any(k in low for k in ("after", "baad", "se pehle nahi")):
            req.earliest_hour = hour
            req.latest_hour = max(hour + 2, req.latest_hour or 0)
        elif any(k in low for k in ("before", "by ", "tak")):
            req.latest_hour = hour
            req.earliest_hour = min(req.earliest_hour or 9, hour - 1)
        else:
            req.earliest_hour, req.latest_hour = hour, hour + 1
    req.complete = req.day is not None and (req.window is not None or req.earliest_hour is not None)
    return req


def describe(req: SlotRequest) -> str:
    """Human-readable summary used in handoff notes."""
    parts = []
    if req.day_word:
        parts.append(req.day.isoformat() if req.day_word == "date" else req.day_word)
    if req.window:
        parts.append(req.window)
    if req.earliest_hour is not None and req.latest_hour is not None:
        parts.append(f"{req.earliest_hour:02d}:00-{req.latest_hour:02d}:00")
    return " ".join(parts) or "no slot given"
