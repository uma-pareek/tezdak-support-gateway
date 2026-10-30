"""LLM cost accounting.

Rates are dollars per million tokens: uncached input $0.10, cached input $0.01, output $0.50.

Changelog
- v1: flat per-token rate.
- v2: cached-token rate split out.
- v2.1: INR conversion helper (rate is a flag, not live FX).
"""
from __future__ import annotations

RATE_INPUT = 0.10
RATE_CACHED = 0.01
RATE_OUTPUT = 0.50
USD_TO_INR = 83.0  # TODO: read from settings once finance gives us a monthly rate


def spend_usd(input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    uncached = max(input_tokens - cached_tokens, 0)
    return (uncached * RATE_INPUT + cached_tokens * RATE_CACHED + output_tokens * RATE_OUTPUT) / 1_000_000


def record_cost_usd(rec) -> float:
    return spend_usd(rec.input_tokens, rec.cached_tokens, rec.output_tokens)


def total_cost_usd(records) -> float:
    return sum(record_cost_usd(r) for r in records)
