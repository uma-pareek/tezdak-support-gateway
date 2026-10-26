"""Small TTL cache used for read tools."""

import json
import time


def make_key(name, args):
    return name + ":" + json.dumps(args, sort_keys=True, default=str)


class TTLCache:
    def __init__(self, clock=time.monotonic, max_entries=256):
        self._clock = clock
        self._max = max_entries
        self._data = {}  # key -> (expires_at, tool_name, value)
        self.hits = 0
        self.misses = 0

    def get(self, name, args):
        key = make_key(name, args)
        item = self._data.get(key)
        if item is None:
            self.misses += 1
            return None
        expires, _, value = item
        if self._clock() >= expires:
            del self._data[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def put(self, name, args, value, ttl_s):
        if ttl_s <= 0:
            return
        if len(self._data) >= self._max:
            self._evict()
        self._data[make_key(name, args)] = (self._clock() + ttl_s, name, value)

    def _evict(self):
        now = self._clock()
        for key in [k for k, v in self._data.items() if v[0] <= now]:
            del self._data[key]
        while len(self._data) >= self._max:
            del self._data[next(iter(self._data))]

    def invalidate_tool(self, name):
        for key in [k for k, v in self._data.items() if v[1] == name]:
            del self._data[key]

    def clear(self):
        self._data.clear()

    def __len__(self):
        return len(self._data)
