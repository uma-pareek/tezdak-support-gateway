"""In-memory log of feature tool dispatches, for debugging and the odd report."""

from collections import Counter
from dataclasses import dataclass


@dataclass
class UsageEntry:
    tool: str
    feature: str
    awb: str | None
    ok: bool
    error: str | None = None


class UsageLog:
    def __init__(self, limit=1000):
        self.limit = limit
        self.entries: list[UsageEntry] = []

    def record(self, tool, feature, awb, result):
        err = result.get("error") if isinstance(result, dict) else None
        self.entries.append(UsageEntry(tool, feature, awb, err is None, err))
        if len(self.entries) > self.limit:
            del self.entries[: len(self.entries) - self.limit]

    def counts(self):
        return dict(Counter(e.tool for e in self.entries))

    def error_counts(self):
        return dict(Counter(e.error for e in self.entries if e.error))

    def summary(self):
        total = len(self.entries)
        bad = sum(1 for e in self.entries if not e.ok)
        return {"calls": total, "errors": bad, "by_tool": self.counts(), "by_error": self.error_counts()}
