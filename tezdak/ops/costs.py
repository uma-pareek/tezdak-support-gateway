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


def cost_per_conversation(records) -> float:
    return total_cost_usd(records) / len(records) if records else 0.0


def usd_to_inr(usd: float, rate: float = USD_TO_INR) -> float:
    return usd * rate


def cost_by_intent(records) -> dict:
    out: dict = {}
    for r in records:
        out[r.intent] = out.get(r.intent, 0.0) + record_cost_usd(r)
    return out


def token_totals(records) -> dict:
    return {
        "input_tokens": sum(r.input_tokens for r in records),
        "cached_tokens": sum(r.cached_tokens for r in records),
        "output_tokens": sum(r.output_tokens for r in records),
        "calls": sum(r.llm_calls for r in records),
    }


def cache_hit_ratio(records) -> float:
    inp = sum(r.input_tokens for r in records)
    return sum(r.cached_tokens for r in records) / inp if inp else 0.0


def project_monthly_usd(records, conversations_per_month: int) -> float:
    """Straight-line projection from the sample's average cost per conversation."""
    return cost_per_conversation(records) * conversations_per_month


def over_budget(records, budget_usd: float) -> bool:
    return total_cost_usd(records) > budget_usd


def cost_table(records) -> list:
    """Rows (scenario, input, cached, output, usd) sorted by cost descending."""
    rows = [(r.scenario, r.input_tokens, r.cached_tokens, r.output_tokens, record_cost_usd(r)) for r in records]
    return sorted(rows, key=lambda row: (-row[4], row[0]))
