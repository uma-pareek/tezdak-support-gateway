"""Hinglish text normalizer.

Changelog
- v1  spelling variants and whitespace cleanup.
- v2  number words ("teen sau" -> 300), date words resolved against a passed `now`.
- v3  tiny devanagari-to-roman table for the most common support words.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# canonical romanized spelling -> variants seen in chats
SPELLING_VARIANTS = {
    "nahi": ("nahin", "nai", "nahii", "nhi", "nahi", "nahee", "nehi"),
    "kahan": ("kaha", "kahaan", "kanha", "kaha"),
    "mila": ("milaa", "mil", "mili", "milla"),
    "aaya": ("aya", "aaya", "ayaa", "aaye", "aye"),
    "kab": ("kb", "kabb"),
    "kal": ("kl",),
    "aaj": ("aj", "aajj"),
    "parso": ("parsu", "parson", "parsoo"),
    "bhejo": ("bhejiye", "bhejiyo", "bhej"),
    "chahiye": ("chahie", "chahiyee", "chaiye", "chahiye"),
    "paisa": ("paise", "paisaa", "pese"),
    "wapas": ("vapas", "wapis", "vapis"),
    "kyun": ("kyu", "kyon", "kyoon"),
    "mera": ("mra", "meraa"),
    "parcel": ("parsel", "parcell", "percel"),
    "delivery": ("delevery", "deliveri", "dilivery"),
    "rider": ("raider", "ridar"),
    "refund": ("rifund", "refnd"),
    "hai": ("h", "he", "hain"),
    "karo": ("kro", "karoo", "kijiye", "kijiyega"),
    "rupaye": ("rupay", "rupaiye", "rupee", "rupees", "rs"),
}

_VARIANT_TO_CANON: dict[str, str] = {}
for _canon, _vars in SPELLING_VARIANTS.items():
    for _v in _vars:
        _VARIANT_TO_CANON.setdefault(_v, _canon)
# "h", "he", "mil", "aye", "bhej", "rs" are too risky as plain words in English text
for _risky in ("h", "he", "mil", "aye", "bhej", "rs", "kl", "aj"):
    _VARIANT_TO_CANON.pop(_risky, None)

DEVANAGARI_WORDS = {
    "कहाँ": "kahan", "कहां": "kahan", "नहीं": "nahi", "मिला": "mila", "पार्सल": "parcel",
    "डिलीवरी": "delivery", "कल": "kal", "आज": "aaj", "परसों": "parso", "रिफंड": "refund",
    "पैसा": "paisa", "पैसे": "paisa", "कब": "kab", "आया": "aaya", "राइडर": "rider",
    "ऑर्डर": "order", "कैंसिल": "cancel", "पता": "address", "वापस": "wapas", "है": "hai",
}

UNITS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "tees": 30, "chalis": 40, "pachas": 50,
}
MULTIPLIERS = {"sau": 100, "hazar": 1000, "hazaar": 1000, "hajar": 1000, "lakh": 100000}
_NUM_PAT = re.compile(
    r"\b(" + "|".join(sorted(UNITS, key=len, reverse=True)) + r")\s+(" + "|".join(MULTIPLIERS) + r")\b",
    re.I,
)
_BARE_MULT = re.compile(r"\b(sau|hazar|hazaar)\b", re.I)

_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF☀-➿️‍]+", re.UNICODE
)
_WS = re.compile(r"\s+")
_REPEAT = re.compile(r"(.)\1{2,}")
_PUNCT_RUN = re.compile(r"([!?.])\1{1,}")

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass
class Normalized:
    text: str
    original: str
    dates: list = field(default_factory=list)   # [(word, date)]
    numbers: list = field(default_factory=list)  # [(phrase, int)]


def strip_emoji(text: str) -> str:
    return _EMOJI.sub(" ", text or "")


def collapse_whitespace(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def squeeze_repeats(text: str) -> str:
    """'nahiiii' -> 'nahii', '!!!' -> '!'. Keeps two letters so 'aaya' survives."""
    text = _REPEAT.sub(lambda m: m.group(1) * 2, text)
    return _PUNCT_RUN.sub(lambda m: m.group(1), text)


def transliterate_devanagari(text: str) -> str:
    for dev, rom in DEVANAGARI_WORDS.items():
        text = text.replace(dev, rom)
    return text


def canonical_word(word: str) -> str:
    return _VARIANT_TO_CANON.get(word.lower(), word.lower())


def number_words_to_digits(text: str) -> tuple[str, list]:
    """Replace '<unit> sau|hazar' phrases by digits. 'teen sau' -> '300'."""
    found = []

    def repl(m):
        val = UNITS[m.group(1).lower()] * MULTIPLIERS[m.group(2).lower()]
        found.append((m.group(0), val))
        return str(val)

    text = _NUM_PAT.sub(repl, text)

    def bare(m):
        val = MULTIPLIERS[m.group(1).lower()]
        found.append((m.group(0), val))
        return str(val)

    # bare "sau" / "hazar" only when it follows a digit run already ("2 hazar" -> 2000)
    text = re.sub(r"\b(\d+)\s+(sau|hazar|hazaar)\b", lambda m: _mul(m, found), text, flags=re.I)
    return text, found


def _mul(m, found):
    val = int(m.group(1)) * MULTIPLIERS[m.group(2).lower()]
    found.append((m.group(0), val))
    return str(val)


def resolve_date_word(word: str, now: datetime | None) -> datetime | None:
    """Map aaj/kal/parso/today/tomorrow to a date at `now`'s offset. None when `now` is missing."""
    if now is None:
        return None
    w = canonical_word(word)
    offsets = {"aaj": 0, "today": 0, "kal": 1, "tomorrow": 1, "tmrw": 1, "tmr": 1, "parso": 2}
    if w == "day" or w == "overmorrow":
        return now + timedelta(days=2)
    if w in offsets:
        return now + timedelta(days=offsets[w])
    if w in WEEKDAYS:
        ahead = (WEEKDAYS.index(w) - now.weekday()) % 7 or 7
        return now + timedelta(days=ahead)
    return None


_PAST_KAL = re.compile(r"\bkal\b[^.?!]{0,40}\b(aaya|gaya|gayi|tha|thi|hua|kiya|nahi\s+aaya)\b", re.I)


def kal_is_yesterday(text: str) -> bool:
    """'kal' means both yesterday and tomorrow. Past-tense verbs near it suggest yesterday."""
    return bool(_PAST_KAL.search(text or ""))


def find_dates(text: str, now: datetime | None) -> list:
    out = []
    if now is None:
        return out
    for m in re.finditer(r"\b(aaj|kal|parso|today|tomorrow|tmrw|tmr|" + "|".join(WEEKDAYS) + r")\b", text, re.I):
        word = m.group(1)
        d = resolve_date_word(word, now)
        if word.lower() == "kal" and kal_is_yesterday(text):
            d = now - timedelta(days=1)
        if d is not None:
            out.append((word.lower(), d.date()))
    return out


def normalize(text: str, now: datetime | None = None) -> Normalized:
    """Clean a raw customer message. Does not change meaning, only spelling and spacing."""
    original = text or ""
    t = strip_emoji(original)
    t = transliterate_devanagari(t)
    t = squeeze_repeats(t.lower())
    t = collapse_whitespace(t)
    t, numbers = number_words_to_digits(t)
    words = re.split(r"(\W+)", t)
    t = "".join(canonical_word(w) if w and w[0].isalpha() else w for w in words)
    return Normalized(text=t, original=original, dates=find_dates(t, now), numbers=numbers)


def normalize_text(text: str, now: datetime | None = None) -> str:
    return normalize(text, now).text


# deprecated: old name kept for callers of the pre-split router helper
def clean(text: str) -> str:
    return normalize_text(text)
