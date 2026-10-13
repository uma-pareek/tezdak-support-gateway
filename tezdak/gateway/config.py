"""Gateway settings with env overrides (`TEZDAK_GW_*`).

Changelog:
  v1  session ttl and dedupe only
  v2  rate limit knobs
  v3  reply split length, voice notes flag
"""

import os
from dataclasses import dataclass, fields

ENV_PREFIX = "TEZDAK_GW_"
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


class GatewayConfigError(ValueError):
    pass


@dataclass(frozen=True)
class GatewayConfig:
    session_ttl_s: int = 6 * 3600
    session_window: int = 12            # last-N messages kept per session
    session_file: str = ""              # empty = memory only
    dedupe_capacity: int = 2000
    dedupe_ttl_s: int = 900
    rate_capacity: int = 5              # burst
    rate_refill_per_s: float = 0.2      # one token per 5 seconds
    max_reply_chars: int = 900
    strip_markdown: bool = True
    use_emoji_map: bool = True
    voice_notes_enabled: bool = True
    whatsapp_window_h: int = 24
    # TODO: per-channel overrides, app chat does not need splitting
    legacy_sms_fallback: bool = False   # dead branch, kept for the old SMS vendor
    rate_limited_reply: str = "Thoda ruk jaiye, aap bahut jaldi messages bhej rahe hain. Please try again in a few seconds."
    voice_failed_reply: str = "Voice note samajh nahi aaya. Kya aap text mein bhej sakte hain?"

    @classmethod
    def from_env(cls, environ=None) -> "GatewayConfig":
        env = os.environ if environ is None else environ
        values = {}
        for f in fields(cls):
            raw = env.get(ENV_PREFIX + f.name.upper())
            if raw is None:
                continue
            values[f.name] = _coerce(f.name, f.type, raw.strip())
        return cls(**values)


def _coerce(name, typ, raw):
    typ = typ if isinstance(typ, str) else getattr(typ, "__name__", str(typ))
    try:
        if typ == "bool":
            low = raw.lower()
            if low in _TRUE:
                return True
            if low in _FALSE:
                return False
            raise ValueError(raw)
        if typ == "int":
            return int(raw)
        if typ == "float":
            return float(raw)
    except ValueError:
        raise GatewayConfigError("bad value for %s%s: %r" % (ENV_PREFIX, name.upper(), raw)) from None
    return raw
