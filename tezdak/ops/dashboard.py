"""Support dashboard built from conversation records.

`resolved_rate` is computed exactly like `tezdak.metrics.Metrics.resolved_rate`: conversations that were closed
without an escalation, divided by all conversations.

Changelog
- v1: counts and rates.
- v2: latency percentiles, intent mix.
- v3: token spend from costs.py; `Dashboard.from_metrics` bridge for the base Metrics object.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import costs


def percentile(values: list, pct: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(int(-(-pct * len(ordered) // 100)), 1)  # ceil without math import
    return float(ordered[min(rank, len(ordered)) - 1])


@dataclass
class Dashboard:
    conversations: int = 0
    closed: int = 0
    escalated: int = 0
    closed_without_escalation: int = 0
    by_intent: dict = field(default_factory=dict)
    latency_p50_ms: float = 0.0
    latency_p90_ms: float = 0.0
    latency_p99_ms: float = 0.0
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    spend_usd: float = 0.0
    avg_turns: float = 0.0

    @property
    def resolved_rate(self) -> float:
        if not self.conversations:
            return 0.0
        return self.closed_without_escalation / self.conversations

    @property
    def escalation_rate(self) -> float:
        return self.escalated / self.conversations if self.conversations else 0.0

    @property
    def intent_mix(self) -> dict:
        if not self.conversations:
            return {}
        return {k: v / self.conversations for k, v in sorted(self.by_intent.items())}

    def to_dict(self) -> dict:
        return {
            "conversations": self.conversations,
            "closed": self.closed,
            "escalated": self.escalated,
            "closed_without_escalation": self.closed_without_escalation,
            "resolved_rate": self.resolved_rate,
            "escalation_rate": self.escalation_rate,
            "by_intent": dict(self.by_intent),
            "intent_mix": self.intent_mix,
            "latency_p50_ms": self.latency_p50_ms,
            "latency_p90_ms": self.latency_p90_ms,
            "latency_p99_ms": self.latency_p99_ms,
            "input_tokens": self.input_tokens,
            "cached_tokens": self.cached_tokens,
            "output_tokens": self.output_tokens,
            "spend_usd": self.spend_usd,
            "avg_turns": self.avg_turns,
        }

    @classmethod
    def from_metrics(cls, metrics) -> "Dashboard":
        """Bridge from a `tezdak.metrics.Metrics` object (no latency or token data there)."""
        return cls(conversations=metrics.conversations, closed=metrics.closed, escalated=metrics.escalated,
                   closed_without_escalation=metrics.closed_without_escalation, by_intent=dict(metrics.by_intent))


def build_dashboard(records: list) -> Dashboard:
    dash = Dashboard()
    latencies: list = []
    turns = 0
    for r in records:
        dash.conversations += 1
        dash.by_intent[r.intent] = dash.by_intent.get(r.intent, 0) + 1
        if r.escalated:
            dash.escalated += 1
        if r.closed:
            dash.closed += 1
            if not r.escalated:
                dash.closed_without_escalation += 1
        latencies.extend(r.latencies_ms)
        turns += r.turns
    dash.latency_p50_ms = percentile(latencies, 50)
    dash.latency_p90_ms = percentile(latencies, 90)
    dash.latency_p99_ms = percentile(latencies, 99)
    totals = costs.token_totals(records)
    dash.input_tokens = totals["input_tokens"]
    dash.cached_tokens = totals["cached_tokens"]
    dash.output_tokens = totals["output_tokens"]
    dash.spend_usd = costs.total_cost_usd(records)
    dash.avg_turns = turns / dash.conversations if dash.conversations else 0.0
    return dash


def format_dashboard(dash: Dashboard) -> str:
    lines = [
        f"conversations: {dash.conversations}",
        f"resolved_rate: {100 * dash.resolved_rate:.1f}%",
        f"escalation_rate: {100 * dash.escalation_rate:.1f}%",
        f"by_intent: {dash.by_intent}",
        f"latency_ms p50/p90/p99: {dash.latency_p50_ms:.0f}/{dash.latency_p90_ms:.0f}/{dash.latency_p99_ms:.0f}",
        f"tokens in/cached/out: {dash.input_tokens}/{dash.cached_tokens}/{dash.output_tokens}",
        f"spend_usd: {dash.spend_usd:.4f}",
    ]
    return "\n".join(lines)


def diff_dashboards(before: Dashboard, after: Dashboard) -> dict:
    """Numeric deltas (after - before) for the headline numbers, used by weekly comparisons."""
    keys = ("conversations", "resolved_rate", "escalation_rate", "latency_p50_ms", "latency_p90_ms",
            "latency_p99_ms", "spend_usd", "avg_turns")
    b, a = before.to_dict(), after.to_dict()
    return {k: a[k] - b[k] for k in keys}


def intent_table(dash: Dashboard) -> list:
    """Rows (intent, count, share) sorted by count descending then name."""
    mix = dash.intent_mix
    return [(k, v, mix[k]) for k, v in sorted(dash.by_intent.items(), key=lambda kv: (-kv[1], kv[0]))]


def to_markdown(dash: Dashboard, title: str = "Support dashboard") -> str:
    lines = [f"# {title}", "", "| metric | value |", "| --- | --- |",
             f"| conversations | {dash.conversations} |",
             f"| resolved_rate | {100 * dash.resolved_rate:.1f}% |",
             f"| escalation_rate | {100 * dash.escalation_rate:.1f}% |",
             f"| latency p50 / p90 / p99 (ms) | {dash.latency_p50_ms:.0f} / {dash.latency_p90_ms:.0f} / {dash.latency_p99_ms:.0f} |",
             f"| spend (USD) | {dash.spend_usd:.4f} |", "", "| intent | count | share |", "| --- | --- | --- |"]
    for name, count, share in intent_table(dash):
        lines.append(f"| {name} | {count} | {100 * share:.1f}% |")
    return "\n".join(lines)
