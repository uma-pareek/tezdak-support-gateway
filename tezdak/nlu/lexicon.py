"""SMS-speak and slang expansion used before rule matching.

Changelog
- v1  small table lifted from the support macros.
- v2  split into whole-word and phrase tables; phrase table runs first.
Kept separate from normalizer.py because the macros team edits this file, not the code.
"""

import re

WORD_EXPANSIONS = {
    "pls": "please", "plz": "please", "plss": "please", "pleaseee": "please", "u": "you", "ur": "your",
    "r": "are", "thx": "thanks", "thnks": "thanks", "tnx": "thanks", "msg": "message", "txn": "transaction",
    "ord": "order", "dlvry": "delivery", "dlvr": "deliver", "delvd": "delivered", "recd": "received",
    "rcvd": "received", "tmrw": "tomorrow", "tmr": "tomorrow", "2moro": "tomorrow", "2day": "today",
    "asap": "as soon as possible", "cust": "customer", "acc": "account", "amt": "amount", "ph": "phone",
    "no.": "number", "addr": "address", "rfnd": "refund", "cncl": "cancel", "sts": "status", "wat": "what",
    "wen": "when", "wr": "where", "hw": "how", "y": "why", "bcz": "because", "cuz": "because",
    "aap": "aap", "pls.": "please", "ok": "ok", "okk": "ok", "okay": "ok", "hmm": "hmm",
}
PHRASE_EXPANSIONS = (
    (re.compile(r"\bwhere r u\b", re.I), "where are you"),
    (re.compile(r"\bwhr is\b", re.I), "where is"),
    (re.compile(r"\bwhat'?s up with\b", re.I), "what is the status of"),
    (re.compile(r"\bno one picked up\b", re.I), "nobody called"),
    (re.compile(r"\bkab tak\b", re.I), "kab"),
    (re.compile(r"\bkahan tak pahuncha\b", re.I), "kahan"),
    (re.compile(r"\bkya hua mere order ko\b", re.I), "status of my order"),
    (re.compile(r"\bhaan ji\b", re.I), "yes"),
    (re.compile(r"\bji haan\b", re.I), "yes"),
)

AFFIRMATIVE = {"yes", "yeah", "yep", "haan", "han", "ha", "ji", "theek", "thik", "sure", "ok", "okay", "done", "sahi"}
NEGATIVE = {"no", "nope", "nahi", "nahin", "mat", "na", "never", "cancel"}


def expand(text: str) -> str:
    """Expand SMS shorthand. Idempotent."""
    t = text or ""
    for pat, repl in PHRASE_EXPANSIONS:
        t = pat.sub(repl, t)
    words = re.split(r"(\s+)", t)
    return "".join(WORD_EXPANSIONS.get(w.lower(), w) if w.strip() else w for w in words)


def is_affirmative(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return bool(words & AFFIRMATIVE) and not (words & NEGATIVE)


def is_negative(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", (text or "").lower()))
    return bool(words & NEGATIVE)


# TODO: confirm with the macros team whether "ok" should ever count as consent for a write.
def yes_no(text: str) -> str | None:
    if is_negative(text):
        return "no"
    if is_affirmative(text):
        return "yes"
    return None
