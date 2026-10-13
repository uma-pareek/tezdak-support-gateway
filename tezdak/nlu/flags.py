"""Engine switch for the NLU facade.

TEZDAK_NLU_ENGINE: v1 (default), v2 or shadow.
"""

import os

ENGINES = ("v1", "v2", "shadow")
DEFAULT_ENGINE = "v1"
ENV_NAME = "TEZDAK_NLU_ENGINE"


def engine_name(env=None) -> str:
    """Return the configured engine, falling back to the default on unknown values."""
    env = os.environ if env is None else env
    raw = (env.get(ENV_NAME) or "").strip().lower()
    return raw if raw in ENGINES else DEFAULT_ENGINE


def is_shadow(env=None) -> bool:
    return engine_name(env) == "shadow"


# TODO: per-channel overrides (app chat could go to v2 first).
def engine_for_channel(channel: str | None, env=None) -> str:
    return engine_name(env)
