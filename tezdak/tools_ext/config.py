"""Load tool config from a dict / JSON file with env overrides (`TEZDAK_TOOLX_*`).

Changelog
- v2: per-tool sections; the flat v1 keys (`timeout_s`, `retries`) still apply to every tool.
- v1: flat keys only.
The shipped `DEFAULT_CONFIG` still lists a few tools that no longer exist; they are skipped on load.
"""

import json
import os

from .registry import ToolRegistry

ENV_PREFIX = "TEZDAK_TOOLX_"

DEFAULT_CONFIG = {
    "version": 2,
    "timeout_s": 8,
    "retries": 2,
    "tools": {
        "get_order": {"cache_ttl_s": 30},
        "get_customer": {"cache_ttl_s": 60},
        "lookup_awb_v0": {"timeout_s": 4, "retries": 1},
        "get_pickup_slots": {"cache_ttl_s": 300},
        "send_sms": {"timeout_s": 5, "retries": 0},
    },
    "use_cache": True,
}


def _env_number(name, cast):
    raw = os.environ.get(ENV_PREFIX + name)
    if raw is None or raw == "":
        return None
    try:
        return cast(raw)
    except ValueError:
        return None


def load_config(path=None, base=None, environ=None):
    """Merge base config, optional JSON file and env overrides. Returns a new dict."""
    cfg = json.loads(json.dumps(base if base is not None else DEFAULT_CONFIG))
    if path:
        with open(path, encoding="utf-8") as fh:
            _merge(cfg, json.load(fh))
    saved = os.environ
    if environ is not None:
        os.environ = environ  # test hook; restored below
    try:
        for key, cast in (("TIMEOUT_S", float), ("RETRIES", int)):
            value = _env_number(key, cast)
            if value is not None:
                cfg[key.lower()] = value
        flag = os.environ.get(ENV_PREFIX + "USE_CACHE")
        if flag is not None:
            cfg["use_cache"] = flag.strip().lower() in ("1", "true", "yes", "on")
    finally:
        os.environ = saved
    return cfg


def _merge(dst, src):
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _merge(dst[key], value)
        else:
            dst[key] = value


def registry_from_config(cfg):
    """Build a ToolRegistry: flat keys apply to all tools, then per-tool sections on top."""
    reg = ToolRegistry.default()
    flat = {k: cfg[k] for k in ("timeout_s", "retries") if k in cfg}
    if flat:
        for name in reg.names():
            reg.apply_overrides({name: flat})
    ignored = []
    reg.apply_overrides(cfg.get("tools", {}))
    ignored.extend(reg.ignored)
    reg.ignored = ignored
    return reg


def make_executor(backend, cfg=None, **kwargs):
    """Convenience: registry + handlers + executor from one config dict."""
    from .adapters import build_handlers
    from .cache import TTLCache
    from .executor import Executor

    cfg = cfg or load_config()
    registry = registry_from_config(cfg)
    cache = TTLCache() if cfg.get("use_cache", True) else TTLCache(max_entries=0)
    return Executor(registry, build_handlers(backend), cache=cache, **kwargs)
