"""Executor: validates args, applies cache, per-tool timeout and retry settings.

`Executor(registry, handlers).call(name, args)` returns a JSON-able dict. Failures come back as
`{"error": code, ...}` rather than exceptions unless `raise_errors=True`.
"""

import concurrent.futures
import copy
import time

from .cache import TTLCache
from .defs import TOOL_DEFS
from .schemas import SchemaError, validate_args


class ToolCallError(Exception):
    def __init__(self, code, detail=""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class Executor:
    def __init__(self, registry, handlers, cache=None, on_event=None, sleep=time.sleep,
                 backoff_s=0.0, raise_errors=False):
        self.registry = registry
        self.handlers = handlers
        self.cache = cache if cache is not None else TTLCache()
        self.on_event = on_event
        self._sleep = sleep
        self.backoff_s = backoff_s
        self.raise_errors = raise_errors
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="toolext")

    def _emit(self, kind, data):
        if self.on_event:
            self.on_event(kind, data)

    def _fail(self, code, **extra):
        if self.raise_errors:
            raise ToolCallError(code, str(extra.get("detail", "")))
        return {"error": code, **extra}

    def _run_once(self, handler, args, timeout_s):
        future = self._pool.submit(handler, copy.deepcopy(args))
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"no result in {timeout_s}s") from None

    def call(self, name, args):
        if not self.registry.has(name) or name not in self.handlers or name not in TOOL_DEFS:
            return self._fail("UNKNOWN_TOOL", tool=name)
        cfg = self.registry.get(name)
        try:
            validate_args(args, TOOL_DEFS[name]["parameters"])
        except SchemaError as exc:
            return self._fail("BAD_ARGS", tool=name, detail="; ".join(exc.errors))

        if not cfg.is_write and cfg.cache_ttl_s > 0:
            cached = self.cache.get(name, args)
            if cached is not None:
                self._emit("tool_cache_hit", {"tool": name})
                return copy.deepcopy(cached)

        self._emit("tool_call", {"tool": name, "args": args})
        attempts = cfg.retries + 1
        last = None
        for attempt in range(1, attempts + 1):
            try:
                result = self._run_once(self.handlers[name], args, cfg.timeout_s)
            except TimeoutError as exc:
                last = exc
                self._emit("tool_timeout", {"tool": name, "attempt": attempt})
                if attempt < attempts and self.backoff_s:
                    self._sleep(self.backoff_s * attempt)
                continue
            except Exception as exc:  # handler bugs surface as a tool error, not a crash
                self._emit("tool_error", {"tool": name, "error": repr(exc)})
                return self._fail("HANDLER_ERROR", tool=name, detail=repr(exc))
            self._emit("tool_result", {"tool": name, "attempt": attempt})
            self._after_success(cfg, name, args, result)
            return result
        return self._fail("TIMEOUT", tool=name, attempts=attempts, detail=str(last))

    def _after_success(self, cfg, name, args, result):
        is_error = isinstance(result, dict) and "error" in result
        if cfg.is_write:
            if not is_error:
                for tool in cfg.invalidates:
                    self.cache.invalidate_tool(tool)
        elif cfg.cache_ttl_s > 0 and not is_error:
            self.cache.put(name, args, copy.deepcopy(result), cfg.cache_ttl_s)

    def close(self):
        self._pool.shutdown(wait=False, cancel_futures=True)


def call_with_tool_v1(executor, name, **args):
    """Deprecated v1-style call: keyword args instead of a dict. Kept for the old agent glue."""
    return executor.call(name, dict(args))
