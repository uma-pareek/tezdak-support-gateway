"""FeaturePlanner: what the agent should add to the prompt and tool list for one message.

Sits between the agent and the registry. Applies the config switches, caps the
number of extra tool specs, and records dispatches in the usage log.

Changelog
  0.3  `FeatureSet` kept as a shim for the first integration sketch.
  0.2  Usage log.
  0.1  Spec selection and hints.
"""

import warnings

from . import extract
from .config import FeatureConfig
from .registry import FeatureRegistry
from .usage import UsageLog


class FeaturePlanner:
    def __init__(self, registry=None, config=None):
        self.config = config or FeatureConfig.from_env()
        self.registry = registry or FeatureRegistry.default()
        self.usage = UsageLog() if self.config.usage_log else None

    def active(self, ctx):
        return [f for f in self.registry.for_context(ctx) if self.config.is_on(f.name)]

    def specs(self, ctx):
        specs = []
        for f in self.active(ctx):
            specs.extend(f.tool_specs())
        return specs[: self.config.max_specs]

    def hint_block(self, ctx):
        lines = []
        for f in self.active(ctx):
            h = f.prompt_hint(ctx)
            if not h:
                continue
            if self.config.flags.get("use_old_hint_format"):
                lines.append("[%s] %s" % (f.name, h))
            else:
                lines.append("- %s: %s" % (f.name, h))
        return "\n".join(lines)

    def suggested_args(self, ctx):
        merged = {}
        for f in self.active(ctx):
            for k, v in extract.prefill(f.name, ctx.user_text, ctx.now).items():
                merged.setdefault(f.name, {})[k] = v
        return merged

    def dispatch(self, name, args, ctx):
        offered = {s["name"] for f in self.active(ctx) for s in f.tool_specs()}
        if name not in offered:
            return {"error": "tool_not_available", "name": name}
        result = self.registry.dispatch(name, args, ctx)
        if self.usage is not None:
            owner = next((f.name for f in self.registry.features if name in {s["name"] for s in f.tool_specs()}), "?")
            self.usage.record(name, owner, (args or {}).get("awb") or ctx.awb, result)
        return result


class FeatureSet(FeaturePlanner):  # pragma: no cover - old name
    """Deprecated: use FeaturePlanner."""

    def __init__(self, *a, **kw):
        warnings.warn("FeatureSet is deprecated, use FeaturePlanner", DeprecationWarning, stacklevel=2)
        super().__init__(*a, **kw)
