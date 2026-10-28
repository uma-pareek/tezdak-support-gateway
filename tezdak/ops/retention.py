"""PII redaction for exported traces: phones and AWBs are masked, structure is kept.

Changelog
- v1: phone masking.
- v2: AWB masking, stable pseudonyms so one AWB maps to one token inside an export.
- v2.1: records and events share one `redact_value` walker.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
AWB_RE = re.compile(r"\bTZ\d{6,}\b")


class Redactor:
    def __init__(self, mask_awb: bool = True, mask_phone: bool = True):
        self.mask_awb = mask_awb
        self.mask_phone = mask_phone
        self._awbs: dict = {}
        self._phones: dict = {}

    def _token(self, table: dict, key: str, prefix: str) -> str:
        if key not in table:
            table[key] = f"{prefix}{len(table) + 1:04d}"
        return table[key]

    def redact_text(self, text: str) -> str:
        if self.mask_awb:
            text = AWB_RE.sub(lambda m: self._token(self._awbs, m.group(0), "AWB-"), text)
        if self.mask_phone:
            text = PHONE_RE.sub(lambda m: self._token(self._phones, re.sub(r"\D", "", m.group(0))[-10:], "PHONE-"), text)
        return text

    def redact_value(self, value):
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, list):
            return [self.redact_value(v) for v in value]
        if isinstance(value, dict):
            return {k: self.redact_value(v) for k, v in value.items()}
        return value

    def redact_events(self, events: list) -> list:
        return [{**ev, "data": self.redact_value(ev["data"])} for ev in events]

    def redact_record(self, rec):
        return replace(rec, awb=self.redact_text(rec.awb), phone=self.redact_text(rec.phone) if rec.phone else "",
                       first_text=self.redact_text(rec.first_text), metadata=self.redact_value(rec.metadata))


def contains_pii(text: str) -> bool:
    return bool(PHONE_RE.search(text) or AWB_RE.search(text))


def export_redacted_dir(src, dst, read_trace, write_trace) -> int:
    """Redact every trace file under `src` into `dst`. Returns the number of files written."""
    redactor = Redactor()
    count = 0
    for path in sorted(Path(src).rglob("*.jsonl")):
        write_trace(redactor.redact_events(read_trace(path)), Path(dst) / path.relative_to(src))
        count += 1
    return count
