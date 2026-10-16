"""Shadow mode: run v1 and v2 on the same text and keep agreement stats in memory.

Nothing in production calls this. The facade only uses it when TEZDAK_NLU_ENGINE=shadow.
"""

import threading
from collections import Counter
from dataclasses import dataclass

from .intents_v2 import classify_v2, map_v1_label
from .rules_v1 import classify_v1


@dataclass
class ShadowRecord:
    text: str
    v1: str
    v2: str
    v2_source: str
    agree: bool


class ShadowLog:
    def __init__(self, max_records: int = 1000):
        self.max_records = max_records
        self._records: list = []
        self._lock = threading.Lock()

    def add(self, rec: ShadowRecord) -> None:
        with self._lock:
            self._records.append(rec)
            if len(self._records) > self.max_records:
                del self._records[: len(self._records) - self.max_records]

    def records(self) -> list:
        with self._lock:
            return list(self._records)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def summary(self) -> dict:
        recs = self.records()
        total = len(recs)
        if not total:
            return {"total": 0, "agreement": None, "disagreements": {}, "v2_sources": {}}
        agree = sum(1 for r in recs if r.agree)
        pairs = Counter((r.v1, r.v2) for r in recs if not r.agree)
        return {
            "total": total,
            "agreement": round(agree / total, 3),
            "disagreements": {f"{a}->{b}": n for (a, b), n in pairs.most_common(10)},
            "v2_sources": dict(Counter(r.v2_source for r in recs)),
        }


DEFAULT_LOG = ShadowLog()


def run_shadow(text, shipment_status=None, llm=None, log: ShadowLog | None = None, now=None) -> ShadowRecord:
    """Classify with both engines and log the pair. Returns the record (v1 is the live answer)."""
    log = DEFAULT_LOG if log is None else log
    v1_label, _ = classify_v1(text, shipment_status)
    v2 = classify_v2(text, llm=llm, shipment_status=shipment_status, now=now)
    rec = ShadowRecord(text=text, v1=v1_label, v2=v2.intent, v2_source=v2.source,
                       agree=map_v1_label(v1_label) == v2.intent)
    log.add(rec)
    return rec


def summary() -> dict:
    return DEFAULT_LOG.summary()
