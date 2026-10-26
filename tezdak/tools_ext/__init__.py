"""Extra tool layer (v2): registry, specs, cache, executor, backend adapters.

Changelog
- v2: per-tool config in the registry, TTL cache for read tools, arg validation.
- v1: lived inside the old tool module; kept there until the lead wires this in.
"""

from .adapters import BackendAdapter, build_handlers
from .cache import TTLCache
from .defs import TOOL_DEFS, tool_spec_list
from .executor import Executor, ToolCallError
from .registry import ToolConfig, ToolRegistry
from .schemas import SchemaError, validate_args

__all__ = [
    "BackendAdapter", "build_handlers", "TTLCache", "TOOL_DEFS", "tool_spec_list",
    "Executor", "ToolCallError", "ToolConfig", "ToolRegistry", "SchemaError", "validate_args",
]
