"""Reply formatting: markdown stripping, emoji map, splitting, quick replies."""

import re

EMOJI_MAP = {
    ":)": "\U0001F642",
    ":(": "\U0001F641",
    "<3": "❤️",
    "(parcel)": "\U0001F4E6",
    "(truck)": "\U0001F69A",
    "(ok)": "✅",
}

_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", re.S)
_CODE = re.compile(r"`([^`]*)`")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*", re.M)
_BULLET = re.compile(r"^\s*[-*]\s+", re.M)
_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
_ETA_LINE = re.compile(r"^ETA:\s*\S+\s*$", re.I | re.M)


def strip_markdown(text: str) -> str:
    text = _LINK.sub(r"\1 (\2)", text)
    text = _BOLD.sub(r"\2", text)
    text = _ITALIC.sub(r"\1", text)
    text = _CODE.sub(r"\1", text)
    text = _HEADING.sub("", text)
    text = _BULLET.sub("- ", text)
    return text


def apply_emoji(text: str) -> str:
    for token, emoji in EMOJI_MAP.items():
        text = text.replace(token, emoji)
    return text


def drop_eta_line(text: str) -> str:
    """The agent's trailing `ETA:` bookkeeping line is not for customers."""
    return _ETA_LINE.sub("", text).rstrip()


def split_reply(text: str, limit: int = 900) -> list:
    """Split on paragraph, then sentence, then hard cut so no part exceeds `limit`."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    parts, current = [], ""
    for piece in _pieces(text, limit):
        joiner = "\n\n" if "\n" in piece or "\n\n" in current else " "
        candidate = piece if not current else current + joiner + piece
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                parts.append(current)
            current = piece
    if current:
        parts.append(current)
    return parts


def _pieces(text, limit):
    for para in re.split(r"\n{2,}", text):
        if len(para) <= limit:
            yield para.strip()
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", para):
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                cut = cut if cut > 0 else limit
                yield sentence[:cut].strip()
                sentence = sentence[cut:].strip()
            if sentence:
                yield sentence


def quick_replies(intent_hint: str = "", language: str = "english") -> list:
    """Suggested buttons (max 3, WhatsApp limit). Chosen from simple reply cues."""
    hint = (intent_hint or "").lower()
    hinglish = language == "hinglish"
    if "slot" in hint or "reschedule" in hint:
        return ["Aaj", "Kal", "Parso"] if hinglish else ["Today", "Tomorrow", "Day after"]
    if "anything else" in hint:
        return ["Haan", "Nahi"] if hinglish else ["Yes", "No"]
    return []


def format_reply(text, strip_md=True, emoji=True, limit=900) -> list:
    text = drop_eta_line(text or "")
    if strip_md:
        text = strip_markdown(text)
    if emoji:
        text = apply_emoji(text)
    return split_reply(text, limit)


# -- small helpers kept from the SMS days (v1) ----------------------------------

def collapse_whitespace(text: str) -> str:
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text or "")).strip()


def preview(text: str, width: int = 60) -> str:
    """One-line preview for logs and notification banners."""
    flat = " ".join((text or "").split())
    return flat if len(flat) <= width else flat[: width - 3].rstrip() + "..."


def sms_safe(text: str) -> str:
    """Deprecated: only used by the legacy SMS fallback path (see GatewayConfig.legacy_sms_fallback)."""
    return text.encode("ascii", "ignore").decode("ascii")[:160]
