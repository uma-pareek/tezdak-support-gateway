"""Language detection for English, Hinglish, Hindi (devanagari) and mixed messages."""

import re
from dataclasses import dataclass

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
LATIN_WORD = re.compile(r"[a-zA-Z]+")

HINGLISH_MARKERS = {
    "hai", "hain", "nahi", "nahin", "nai", "kab", "kahan", "kaha", "kidhar", "mera", "meri", "mere", "mujhe",
    "aaya", "aayi", "aaye", "kal", "aaj", "parso", "karo", "kijiye", "kijiyega", "bhej", "bhejo", "dijiye",
    "abhi", "kya", "mila", "aap", "kar", "ho", "gaya", "gayi", "toh", "to", "bhi", "paisa", "paise", "wapas",
    "chahiye", "kyun", "kyu", "se", "ka", "ki", "ke", "par", "pe", "mein", "me", "koi", "kuch", "bahut",
    "jaldi", "gaye", "kat", "rupaye", "sau", "hazar", "bhai", "sir", "yaar", "tha", "thi", "raha", "rahi", "baad", "pehle", "phir", "dena", "do",
}
# words that look Hindi but are also very common English tokens
AMBIGUOUS = {"to", "do", "me", "sir", "ho", "se", "par", "kar"}
ENGLISH_MARKERS = {
    "the", "is", "my", "where", "when", "order", "parcel", "please", "not", "have", "has", "was", "will",
    "can", "you", "your", "delivery", "delivered", "refund", "received", "package", "tomorrow", "today",
    "and", "for", "with", "this", "that", "what", "why", "how", "it", "of", "in", "on", "me", "to",
}


@dataclass
class LanguageResult:
    label: str          # english | hinglish | hindi | mixed
    confidence: float
    hinglish_hits: int = 0
    english_hits: int = 0


def devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if DEVANAGARI.match(c)) / len(letters)


def detect_language(text: str) -> LanguageResult:
    t = text or ""
    ratio = devanagari_ratio(t)
    words = [w.lower() for w in LATIN_WORD.findall(t)]
    hi = sum(1 for w in words if w in HINGLISH_MARKERS and w not in AMBIGUOUS)
    weak = sum(1 for w in words if w in AMBIGUOUS)
    en = sum(1 for w in words if w in ENGLISH_MARKERS)
    if ratio >= 0.6:
        return LanguageResult("hindi", min(0.99, 0.6 + ratio / 2.5), hi, en)
    if ratio > 0.0 and words:
        return LanguageResult("mixed", 0.6, hi, en)
    if not words:
        return LanguageResult("english", 0.3, 0, 0)
    if hi == 0:
        conf = 0.55 + min(0.4, en / max(len(words), 1))
        # a lone weak token is not evidence of Hinglish
        return LanguageResult("english", round(min(conf, 0.97), 2), 0, en)
    share = (hi + weak * 0.3) / len(words)
    if en >= 3 and share < 0.25:
        return LanguageResult("mixed", 0.55, hi, en)
    return LanguageResult("hinglish", round(min(0.95, 0.55 + share), 2), hi, en)


def is_hinglish_like(text: str) -> bool:
    return detect_language(text).label in ("hinglish", "mixed", "hindi")


def reply_language(label: str) -> str:
    """Language a reply should use. Devanagari and mixed senders get Hinglish replies."""
    return "english" if label == "english" else "hinglish"
