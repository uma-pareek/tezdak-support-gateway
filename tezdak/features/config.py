"""Feature switches. Defaults first, environment overrides on top.

Env
  TEZDAK_FEATURES_ENABLED   comma list of feature names, or "all" (default)
  TEZDAK_FEATURES_DISABLED  comma list removed after the enabled list is applied
  TEZDAK_FEATURES_MAX_SPECS cap on tool specs offered per message (default 12)
  TEZDAK_FEATURES_USAGE_LOG "1" keeps an in-memory dispatch log (default 1)

Changelog
  0.2  MAX_SPECS cap so the prompt does not grow with every feature.
  0.1  Enabled/disabled lists.
"""

import os
from dataclasses import dataclass, field

DEFAULT_MAX_SPECS = 12
LEGACY_FLAGS = {"use_old_hint_format": False, "strict_awb_check": True}  # strict_awb_check is read by nobody now


def _csv(raw):
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


@dataclass
class FeatureConfig:
    enabled: tuple = ("all",)
    disabled: tuple = ()
    max_specs: int = DEFAULT_MAX_SPECS
    usage_log: bool = True
    flags: dict = field(default_factory=lambda: dict(LEGACY_FLAGS))

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        enabled = tuple(_csv(env.get("TEZDAK_FEATURES_ENABLED"))) or ("all",)
        disabled = tuple(_csv(env.get("TEZDAK_FEATURES_DISABLED")))
        try:
            cap = int(env.get("TEZDAK_FEATURES_MAX_SPECS", DEFAULT_MAX_SPECS))
        except ValueError:
            cap = DEFAULT_MAX_SPECS
        return cls(enabled=enabled, disabled=disabled, max_specs=max(cap, 1),
                   usage_log=env.get("TEZDAK_FEATURES_USAGE_LOG", "1") != "0")

    def is_on(self, name):
        if name in self.disabled:
            return False
        return "all" in self.enabled or name in self.enabled
