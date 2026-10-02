"""Keyword intent router for incoming customer messages (English and Hinglish)."""

import re

INTENTS = ("wismo", "not_received_after_delivered", "reschedule_request", "ndr_complaint", "other")

_NDR = re.compile(
    r"rider\s+(aaya|aayi|nahi\s+aaya|never)|nobody\s+(came|visited)|no\s*one\s+(came|visited)"
    r"|(didn'?t|did\s+not|never)\s+(come|visit|show)|failed\s+(delivery|attempt)|\bndr\b"
    r"|not\s+attempted|attempt\s+(nahi|not)|koi\s+nahi\s+aaya|call\s+nahi\s+(kiya|aaya)"
    r"|delivery\s+boy\s+(nahi|never)|fake\s+attempt",
    re.I,
)
_NOT_RECEIVED = re.compile(
    r"(not|n'?t)\s+(received|got|get)|haven'?t\s+(received|got)|never\s+(received|got)|nahi\s+(mila|aaya|pahuncha)|nahin\s+mila|never\s+arrived",
    re.I,
)
_DELIVERED = re.compile(r"deliver(ed|y\s+ho\s+gaya)|deliver\s+ho\s+gaya|marked\s+delivered|delivered\s+dikha", re.I)
_RESCHEDULE = re.compile(
    r"re-?schedule|re-?attempt|deliver\s+(it\s+)?(today|tomorrow|tmrw|on)|(aaj|kal|parso)\s+(deliver|bhej|de\s+do|karo)"
    r"|deliver\s+kar(o|na|dena)|another\s+(attempt|try)|try\s+again|slot|baad\s+mein\s+deliver|phir\s+se\s+deliver"
    r"|\b(kal|aaj|tomorrow|tmrw)\b.*\b(bhejo|bhej\s+do|de\s+do|karna|karo)\b",
    re.I,
)
_WISMO = re.compile(
    r"where\s+is|where'?s|\bstatus\b|track|kahan|kidhar|when\s+(will|is|does)|\bkab\b|eta\b|update\s+on|kitne\s+din|any\s+update",
    re.I,
)


def classify(text: str, shipment_status: str | None = None) -> str:
    """Return one of INTENTS for a single customer message."""
    t = text or ""
    if _NOT_RECEIVED.search(t) and (_DELIVERED.search(t) or shipment_status == "DELIVERED"):
        return "not_received_after_delivered"
    if _NDR.search(t):
        return "ndr_complaint"
    if _RESCHEDULE.search(t):
        return "reschedule_request"
    if _WISMO.search(t) or _NOT_RECEIVED.search(t):
        return "wismo"
    return "other"


HINGLISH_WORDS = {
    "hai", "nahi", "nahin", "kab", "kahan", "kidhar", "mera", "meri", "mujhe", "aaya", "aayi",
    "kal", "aaj", "karo", "kijiye", "bhej", "bhejo", "dijiye", "abhi", "kya", "mila", "aap", "kar",
}


def detect_language(text: str) -> str:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return "hinglish" if words & HINGLISH_WORDS else "english"
