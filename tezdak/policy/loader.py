"""Pick a policy generation. `TEZDAK_POLICY_GEN` selects it, default v2."""

import os

from .v1_legacy import PolicyV1
from .v2_table import PolicyV2
from .v3_memo import PolicyV3

DEFAULT_GEN = "v2"
ENV_VAR = "TEZDAK_POLICY_GEN"

_REGISTRY = {"v1": PolicyV1, "v2": PolicyV2, "v3": PolicyV3}
_ALIASES = {"legacy": "v1", "table": "v2", "memo": "v3"}


def available() -> list:
    return sorted(_REGISTRY)


def load_policy(name=None):
    chosen = (name or os.environ.get(ENV_VAR) or DEFAULT_GEN).strip().lower()
    chosen = _ALIASES.get(chosen, chosen)
    if chosen not in _REGISTRY:
        raise ValueError(f"unknown policy generation {chosen!r}, expected one of {available()}")
    return _REGISTRY[chosen]()


def load_policy_v1_compat(name=None):
    """Deprecated shim, old callers used this name. Use load_policy."""
    return load_policy(name)
