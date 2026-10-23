"""Per-tool configuration registry.

Changelog
- v2: owner field added; `invalidates` lets a write drop cached reads.
- v1: one global timeout/retry pair. `DEFAULT_TIMEOUT_S` / `DEFAULT_RETRIES` still serve as the fallback.
TODO: load overrides from the settings service instead of a literal dict.
"""

import dataclasses

from .defs import TOOL_DEFS

DEFAULT_TIMEOUT_S = 8
DEFAULT_RETRIES = 2


@dataclasses.dataclass
class ToolConfig:
    name: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    retries: int = DEFAULT_RETRIES
    cache_ttl_s: float = 0
    is_write: bool = False
    owner: str = "support-platform"
    invalidates: tuple = ()


# Tool name -> (is_write, cache_ttl_s, owner, invalidates)
_BASE_TABLE = {
    "get_order": (False, 30, "orders-team", ()),
    "update_address": (True, 0, "orders-team", ("get_order",)),
    "cancel_order": (True, 0, "orders-team", ("get_order",)),
    "create_ticket": (True, 0, "support-platform", ()),
    "get_customer": (False, 60, "crm-team", ()),
    "add_ticket_note": (True, 0, "support-platform", ()),
    "send_template_message": (True, 0, "messaging", ()),
}

# Entries for tools that were removed; kept so old config files still load.
STALE_TOOLS = {
    "lookup_awb_v0": {"timeout_s": 4, "retries": 1},
    "get_pickup_slots": {"timeout_s": 8, "retries": 2},
    "send_sms": {"timeout_s": 5, "retries": 0},
}


class ToolRegistry:
    def __init__(self, configs=None):
        self._configs = dict(configs or {})

    @classmethod
    def default(cls, overrides=None):
        """Every known tool gets timeout_s=8, retries=2; `overrides` is {tool: {field: value}}."""
        configs = {}
        for name, (is_write, ttl, owner, inval) in _BASE_TABLE.items():
            configs[name] = ToolConfig(name=name, cache_ttl_s=ttl, is_write=is_write,
                                       owner=owner, invalidates=inval)
        reg = cls(configs)
        reg.apply_overrides(overrides or {})
        return reg

    def apply_overrides(self, overrides):
        """Apply field overrides; entries for stale or unknown tools are recorded but not registered."""
        self.ignored = []
        fields = {f.name for f in dataclasses.fields(ToolConfig)}
        for name, values in overrides.items():
            cfg = self._configs.get(name)
            if cfg is None:
                self.ignored.append(name)
                continue
            for key, value in values.items():
                if key in fields and key != "name":
                    setattr(cfg, key, value)

    def get(self, name):
        try:
            return self._configs[name]
        except KeyError:
            raise KeyError(f"unknown tool {name!r}") from None

    def has(self, name):
        return name in self._configs

    def names(self):
        return list(self._configs)

    def writes(self):
        return [n for n, c in self._configs.items() if c.is_write]

    def reads(self):
        return [n for n, c in self._configs.items() if not c.is_write]

    def by_owner(self, owner):
        return [n for n, c in self._configs.items() if c.owner == owner]

    def missing_defs(self):
        """Registered tools that have no spec (should be empty)."""
        return [n for n in self._configs if n not in TOOL_DEFS]


def describe(registry):
    """One line per tool for the admin console."""
    lines = []
    for name in sorted(registry.names()):
        c = registry.get(name)
        kind = "write" if c.is_write else "read"
        lines.append(f"{name:<24}{kind:<6} timeout={c.timeout_s}s retries={c.retries} "
                     f"cache={c.cache_ttl_s}s owner={c.owner}")
    return "\n".join(lines)
