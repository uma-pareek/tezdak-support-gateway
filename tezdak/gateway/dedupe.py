"""Message id dedupe: LRU bounded, entries also expire after a TTL."""

import time
from collections import OrderedDict


class Deduper:
    def __init__(self, capacity=2000, ttl_s=900, clock=time.monotonic):
        if capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.capacity = capacity
        self.ttl_s = ttl_s
        self._clock = clock
        self._seen = OrderedDict()   # id -> first seen time
        self.hits = 0

    def _evict_expired(self, now):
        while self._seen:
            key, seen_at = next(iter(self._seen.items()))
            if now - seen_at <= self.ttl_s:
                break
            del self._seen[key]

    def seen(self, message_id) -> bool:
        """Record the id; return True if it was already present (a duplicate)."""
        if not message_id:
            return False
        now = self._clock()
        self._evict_expired(now)
        if message_id in self._seen:
            self._seen.move_to_end(message_id)
            self.hits += 1
            return True
        self._seen[message_id] = now
        while len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        return False

    def __len__(self):
        return len(self._seen)
