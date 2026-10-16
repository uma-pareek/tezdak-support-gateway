"""Token buket per phone."""

import time


class TokenBucket:
    def __init__(self, capacity, refill_per_s, clock=time.monotonic):
        self.capacity = float(capacity)
        self.refill_per_s = float(refill_per_s)
        self._clock = clock
        self.tokens = float(capacity)
        self.updated = clock()

    def _refill(self):
        now = self._clock()
        self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.refill_per_s)
        self.updated = now

    def take(self, n=1) -> bool:
        self._refill()
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False

    def wait_s(self, n=1) -> float:
        self._refill()
        if self.tokens >= n or self.refill_per_s <= 0:
            return 0.0
        return (n - self.tokens) / self.refill_per_s


class RateLimiter:
    def __init__(self, capacity=5, refill_per_s=0.2, clock=time.monotonic, max_phones=10000):
        self.capacity = capacity
        self.refill_per_s = refill_per_s
        self.max_phones = max_phones
        self._clock = clock
        self._buckets = {}

    def allow(self, phone) -> bool:
        bucket = self._buckets.get(phone)
        if bucket is None:
            if len(self._buckets) >= self.max_phones:
                self._prune()
            bucket = self._buckets[phone] = TokenBucket(self.capacity, self.refill_per_s, self._clock)
        return bucket.take()

    def wait_s(self, phone) -> float:
        bucket = self._buckets.get(phone)
        return bucket.wait_s() if bucket else 0.0

    def _prune(self):
        """Drop buckets that have fully refilled; they carry no information."""
        for phone in [p for p, b in self._buckets.items() if (b._refill() or b.tokens >= b.capacity)]:
            del self._buckets[phone]
