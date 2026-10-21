"""Voice note placeholder. No audio is processed and nothing touches the network.

`transcribe` looks the media id up in a canned table. A real speech-to-text vendor
is not wired in yet.
"""

CANNED_TRANSCRIPTS = {
    "vn-wismo-1": "mera parcel kahan hai TZ482915",
    "vn-wismo-2": "bhaiya order abhi tak nahi aaya, kab tak milega?",
    "vn-resched-1": "kal subah delivery kar dena please TZ482915",
    "vn-ndr-1": "rider aaya hi nahi aur app mein attempt dikha raha hai",
    "vn-refund-1": "I want my money back for TZ550123",
    "vn-noise-1": "",
}


class TranscriptionError(Exception):
    pass


def transcribe(media, table=None) -> str:
    """Return text for an audio media dict ({"id": ...}) or raise TranscriptionError."""
    table = CANNED_TRANSCRIPTS if table is None else table
    media_id = media.get("id") if isinstance(media, dict) else str(media)
    if media_id not in table:
        raise TranscriptionError("no transcript for media %r" % (media_id,))
    text = table[media_id].strip()
    if not text:
        raise TranscriptionError("empty transcript for media %r" % (media_id,))
    return text


def transcribe_all(media_list, table=None):
    """Transcribe every audio item; returns (texts, failed_ids)."""
    texts, failed = [], []
    for item in media_list:
        if item.get("kind") != "audio":
            continue
        try:
            texts.append(transcribe(item, table))
        except TranscriptionError:
            failed.append(item.get("id"))
    return texts, failed
