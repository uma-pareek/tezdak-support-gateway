"""Entity extraction: AWB, pincode, phone, amount, relative dates, time-of-day words."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

from .normalizer import find_dates, normalize

AWB_RE = re.compile(r"\bTZ\d{6,}\b", re.I)
PINCODE_RE = re.compile(r"(?<![\d])[1-9]\d{5}(?![\d])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")
AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr|rupees?|rupaye)\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:rs\.?|rupees?|rupaye|inr|₹)\b",
    re.I,
)

TIME_OF_DAY = {
    "morning": ("morning", "subah", "savere", "am"),
    "afternoon": ("afternoon", "dopahar", "dupahar", "lunch"),
    "evening": ("evening", "shaam", "sham", "after work"),
    "night": ("night", "raat", "late"),
}
_CLOCK = re.compile(r"\b(?:after|before|by|at|tak|baad)?\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm|baje)\b", re.I)


@dataclass
class Entities:
    awbs: list = field(default_factory=list)
    pincodes: list = field(default_factory=list)
    phones: list = field(default_factory=list)
    amounts: list = field(default_factory=list)
    dates: list = field(default_factory=list)       # [(word, date)]
    times_of_day: list = field(default_factory=list)
    clock_times: list = field(default_factory=list)  # [(hour24, minute)]

    @property
    def awb(self) -> str | None:
        return self.awbs[0] if self.awbs else None

    def to_dict(self) -> dict:
        return {
            "awbs": list(self.awbs), "pincodes": list(self.pincodes), "phones": list(self.phones),
            "amounts": list(self.amounts),
            "dates": [(w, d.isoformat() if isinstance(d, date) else str(d)) for w, d in self.dates],
            "times_of_day": list(self.times_of_day),
            "clock_times": [list(c) for c in self.clock_times],
        }


def extract_awbs(text: str) -> list:
    return _dedupe(m.group(0).upper() for m in AWB_RE.finditer(text or ""))


def extract_phones(text: str) -> list:
    out = []
    for m in PHONE_RE.finditer(text or ""):
        out.append(re.sub(r"[\s-]", "", m.group(1)))
    return _dedupe(out)


def extract_pincodes(text: str) -> list:
    """6 digit pincodes. Digits inside an AWB or a phone number are not pincodes."""
    t = AWB_RE.sub(" ", text or "")
    t = PHONE_RE.sub(" ", t)
    return _dedupe(m.group(0) for m in PINCODE_RE.finditer(t))


def extract_amounts(text: str) -> list:
    """Rupee amounts, integers. Accepts 'rs 300', '300 rupees', 'Rs.1,200', '₹50'."""
    out = []
    for m in AMOUNT_RE.finditer(text or ""):
        raw = (m.group(1) or m.group(2)).replace(",", "")
        if raw.isdigit():
            out.append(int(raw))
    return out


def extract_time_of_day(text: str) -> list:
    low = (text or "").lower()
    out = []
    for label, words in TIME_OF_DAY.items():
        for w in words:
            if w == "am":
                continue
            if re.search(r"\b" + re.escape(w) + r"\b", low):
                out.append(label)
                break
    return out


def extract_clock_times(text: str) -> list:
    out = []
    for m in _CLOCK.finditer(text or ""):
        hour, minute, suffix = int(m.group(1)), int(m.group(2) or 0), m.group(3).lower()
        if hour > 12 or minute > 59:
            continue
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        out.append((hour, minute))
    return out


def _dedupe(items) -> list:
    seen, out = set(), []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def extract(text: str, now: datetime | None = None) -> Entities:
    """Run all extractors over the raw text (numbers in words are resolved first for amounts)."""
    raw = text or ""
    norm = normalize(raw, now)
    return Entities(
        awbs=extract_awbs(raw),
        pincodes=extract_pincodes(raw),
        phones=extract_phones(raw),
        amounts=extract_amounts(norm.text) or extract_amounts(raw),
        dates=find_dates(norm.text, now),
        times_of_day=extract_time_of_day(norm.text),
        clock_times=extract_clock_times(norm.text),
    )
