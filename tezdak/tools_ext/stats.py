"""Call log and per-tool counters, fed by the executor's `on_event` hook."""

import collections


class CallStats:
    def __init__(self, keep_last=200):
        self.counts = collections.defaultdict(collections.Counter)  # tool -> event kind -> n
        self.recent = collections.deque(maxlen=keep_last)

    def on_event(self, kind, data):
        tool = data.get("tool", "?")
        self.counts[tool][kind] += 1
        self.recent.append((kind, tool))

    def total(self, kind):
        return sum(c[kind] for c in self.counts.values())

    def tools_with(self, kind):
        return sorted(t for t, c in self.counts.items() if c[kind])

    def summary(self):
        return {
            "tools": {t: dict(c) for t, c in sorted(self.counts.items())},
            "calls": self.total("tool_call"),
            "timeouts": self.total("tool_timeout"),
            "cache_hits": self.total("tool_cache_hit"),
            "errors": self.total("tool_error"),
        }

    def reset(self):
        self.counts.clear()
        self.recent.clear()
