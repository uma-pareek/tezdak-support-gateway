"""Feature flags: defaults, optional JSON file, then env overrides (`TEZDAK_FLAG_<NAME>`).

Changelog:
  v1  plain dict of booleans
  v2  env overrides, typed coercion
  v3  stale flags kept for old dashboards; see STALE_FLAGS
"""

import json
import os

DEFAULT_FLAGS = {
    "address_update": True,
    "cancel_order": True,
    "cod_refund": True,
    "rider_feedback": True,
    "slot_picker": True,
    "delay_notifier": False,
    "promise_tracker": True,
    "handoff": True,
    "not_received_helper": True,
    "wismo_detail": True,
    "voice_notes": False,
    # stale: nothing reads these any more
    "legacy_refund_flow": False,
    "new_ndr_banner": True,
    "whatsapp_templates_v1": True,
    "sms_fallback": False,
}

STALE_FLAGS = ("legacy_refund_flow", "new_ndr_banner", "whatsapp_templates_v1", "sms_fallback")
ENV_PREFIX = "TEZDAK_FLAG_"
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")


def _coerce(raw: str, fallback: bool) -> bool:
    low = raw.strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    return fallback


class FlagService:
    def __init__(self, flags: dict | None = None, environ=None, path: str | None = None):
        self._env = os.environ if environ is None else environ
        self._base = dict(DEFAULT_FLAGS)
        if path:
            self.load_file(path)
        if flags:
            self._base.update({k: bool(v) for k, v in flags.items()})

    def load_file(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            return
        if isinstance(data, dict):
            self._base.update({k: bool(v) for k, v in data.items()})

    def is_enabled(self, name: str, default: bool = False) -> bool:
        fallback = self._base.get(name, default)
        raw = self._env.get(ENV_PREFIX + name.upper())
        if raw is None:
            return fallback
        return _coerce(raw, fallback)

    def set(self, name: str, value: bool) -> None:
        self._base[name] = bool(value)

    def all(self) -> dict:
        return {name: self.is_enabled(name) for name in sorted(self._base)}

    def active(self) -> list[str]:
        return [n for n, on in self.all().items() if on and n not in STALE_FLAGS]

    def stale(self) -> list[str]:
        return [n for n in STALE_FLAGS if n in self._base]
