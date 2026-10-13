"""Per-phone sessions with TTL, active AWB tracking and a last-N message window.

Memory by default; an optional JSON file backend persists on every change.
TODO: the file backend rewrites the whole file, fine for one process only.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field

AWB_RE = re.compile(r"\bTZ\d{6,}\b")


@dataclass
class Session:
    phone: str
    channel: str = "whatsapp"
    awb: str = ""
    messages: list = field(default_factory=list)    # [{"role","content"}]
    last_inbound_ts: float = 0.0                    # epoch seconds
    created: float = 0.0
    touched: float = 0.0

    def to_conversation(self) -> dict:
        """The dict handed to `agent_handle`."""
        return {"messages": [dict(m) for m in self.messages], "awb": self.awb or None}


class SessionStore:
    def __init__(self, ttl_s=6 * 3600, window=12, path="", clock=time.time):
        self.ttl_s = ttl_s
        self.window = window
        self.path = path
        self._clock = clock
        self._sessions = {}
        if path and os.path.exists(path):
            self._load()

    def get(self, phone):
        sess = self._sessions.get(phone)
        if sess and self._clock() - sess.touched > self.ttl_s:
            del self._sessions[phone]
            self._save()
            return None
        return sess

    def get_or_create(self, phone, channel="whatsapp") -> Session:
        sess = self.get(phone)
        if sess is None:
            now = self._clock()
            sess = Session(phone=phone, channel=channel, created=now, touched=now)
            self._sessions[phone] = sess
        sess.channel = channel
        return sess

    def add_message(self, phone, role, content, channel="whatsapp", inbound=False) -> Session:
        sess = self.get_or_create(phone, channel)
        sess.messages.append({"role": role, "content": content})
        if len(sess.messages) > self.window:
            del sess.messages[: len(sess.messages) - self.window]
        now = self._clock()
        sess.touched = now
        if inbound:
            sess.last_inbound_ts = now
            found = AWB_RE.search(content or "")
            if found:
                sess.awb = found.group(0)
        self._save()
        return sess

    def set_awb(self, phone, awb):
        sess = self.get_or_create(phone)
        sess.awb = awb
        self._save()

    def purge_expired(self) -> int:
        now = self._clock()
        stale = [p for p, s in self._sessions.items() if now - s.touched > self.ttl_s]
        for phone in stale:
            del self._sessions[phone]
        if stale:
            self._save()
        return len(stale)

    def __len__(self):
        return len(self._sessions)

    def _save(self):
        if not self.path:
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({p: s.__dict__ for p, s in self._sessions.items()}, fh)
        os.replace(tmp, self.path)

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, ValueError):
            return   # a corrupt file just means everyone starts a fresh session
        for phone, data in raw.items():
            try:
                self._sessions[phone] = Session(**data)
            except TypeError:
                continue


def open_store(path="", **kwargs) -> SessionStore:
    """Deprecated shim from v1: use SessionStore(...) directly."""
    return SessionStore(path=path, **kwargs)
