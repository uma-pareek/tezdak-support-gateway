"""Pull candidate tool arguments out of the customer's text.

These are hints for the model, not decisions: callers still validate. Works on
English and Hinglish text. Standard library regexes only.

Changelog
  0.3  Rating words (paanch, char) understood.
  0.2  Slot words for Hinglish (aaj, kal, parso).
  0.1  VPA and rating.
"""

import re
from datetime import timedelta

from .util import AWB_RE, VPA_RE

VPA_FIND = re.compile(r"[a-zA-Z0-9._-]{2,64}@[a-zA-Z]{2,32}")
AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹|rupees?)\s*(\d[\d,]*)|(\d[\d,]*)\s*(?:rs\.?|inr|₹|rupees?|rupaye|rupay)", re.I)
RATING_NUM = re.compile(r"\b([1-5])\s*(?:/\s*5|star|stars|out of 5|rating)\b|rating\s*(?:of|is|hai)?\s*([1-5])\b", re.I)
RATING_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4,
                "paanch": 5, "panch": 5}
RATING_WORD_RE = re.compile(r"\b(" + "|".join(RATING_WORDS) + r")\s*(?:star|stars|/\s*5|out of 5)", re.I)
SLOT_WORDS = (("parso", 2), ("day after", 2), ("kal", 1), ("tomorrow", 1), ("aaj", 0), ("today", 0))
ISO_IN_TEXT = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
PIN_RE = re.compile(r"\b\d{6}\b")
ADDRESS_MARKERS = re.compile(r"(?:new address|address change|address badal|naya address|deliver (?:it )?to)\s*[:\-]?\s*(.+)", re.I)


def find_awb(text):
    m = AWB_RE.search(text or "")
    return m.group(0).upper() if m else None


def find_vpa(text):
    for m in VPA_FIND.finditer(text or ""):
        if VPA_RE.match(m.group(0)):
            return m.group(0)
    return None


def find_amount(text):
    m = AMOUNT_RE.search(text or "")
    if not m:
        return None
    raw = (m.group(1) or m.group(2)).replace(",", "")
    return int(raw) if raw.isdigit() else None


def find_rating(text):
    m = RATING_NUM.search(text or "")
    if m:
        return int(m.group(1) or m.group(2))
    m = RATING_WORD_RE.search(text or "")
    return RATING_WORDS[m.group(1).lower()] if m else None


def find_slot(text, now=None):
    t = (text or "").lower()
    iso = ISO_IN_TEXT.search(t)
    if iso:
        return iso.group(1)
    for word, offset in SLOT_WORDS:
        if re.search(r"\b" + re.escape(word) + r"\b", t):
            if offset == 0:
                return "today"
            if offset == 1:
                return "tomorrow"
            if now is not None:
                return (now.date() + timedelta(days=offset)).isoformat()
            return None
    return None


def find_address(text):
    m = ADDRESS_MARKERS.search(text or "")
    if m:
        return " ".join(m.group(1).split())
    if PIN_RE.search(text or "") and len((text or "").split()) >= 6:
        return " ".join(text.split())
    return None


def prefill(feature_name, text, now=None):
    """Return a dict of argument guesses for the tools of one feature."""
    out = {}
    awb = find_awb(text)
    if awb:
        out["awb"] = awb
    if feature_name == "cod_refund":
        for k, v in (("vpa", find_vpa(text)), ("amount_inr", find_amount(text))):
            if v:
                out[k] = v
    elif feature_name == "rider_feedback":
        r = find_rating(text)
        if r:
            out["rating"] = r
    elif feature_name == "slot_picker":
        s = find_slot(text, now)
        if s:
            out["slot"] = s
    elif feature_name == "address_update":
        a = find_address(text)
        if a:
            out["new_address"] = a
    return out
