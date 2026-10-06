"""Layered settings: built-in defaults < JSON file < environment (`TEZDAK_SETTING_<KEY>`).

A few keys are stale (kept so old config files still load) and are reported by `stale_keys()`.
"""

import json
import os

DEFAULTS = {
    "hub_cutoff_hour": 11,
    "max_attempts": 3,
    "address_change_window_hours": 24,
    "ticket_sla_hours": 48,
    "goodwill_default_inr": 50,
    "default_language": "english",
    "support_phone": "+91-80000-00000",
    "business_hours": "09:00-21:00",
    # stale keys
    "refund_sla_days": 7,
    "legacy_ticket_prefix": "TZT-",
    "sms_sender_id": "TZDAK",
}
STALE_KEYS = ("refund_sla_days", "legacy_ticket_prefix", "sms_sender_id")
ENV_PREFIX = "TEZDAK_SETTING_"
SOURCES = ("default", "file", "env", "override")


class SettingsError(KeyError):
    pass


def _coerce_like(raw: str, sample):
    if isinstance(sample, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(sample, int):
        try:
            return int(raw)
        except ValueError:
            return sample
    return raw


class Settings:
    def __init__(self, file_values: dict | None = None, environ=None, overrides: dict | None = None):
        self._env = os.environ if environ is None else environ
        self._file = dict(file_values or {})
        self._overrides = dict(overrides or {})

    def load_file(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8") as fh:
                self._file.update(json.load(fh))
        except FileNotFoundError:
            pass

    def _lookup(self, key: str):
        if key in self._overrides:
            return self._overrides[key], "override"
        raw = self._env.get(ENV_PREFIX + key.upper())
        if raw is not None:
            return _coerce_like(raw, DEFAULTS.get(key, "")), "env"
        if key in self._file:
            return self._file[key], "file"
        if key in DEFAULTS:
            return DEFAULTS[key], "default"
        raise SettingsError(key)

    def get(self, key: str, default=None):
        try:
            return self._lookup(key)[0]
        except SettingsError:
            return default

    def source_of(self, key: str) -> str:
        return self._lookup(key)[1]

    def set(self, key: str, value) -> None:
        self._overrides[key] = value

    def as_dict(self) -> dict:
        keys = set(DEFAULTS) | set(self._file) | set(self._overrides)
        return {k: self.get(k) for k in sorted(keys)}

    def stale_keys(self) -> list[str]:
        return [k for k in STALE_KEYS if k in DEFAULTS or k in self._file]
