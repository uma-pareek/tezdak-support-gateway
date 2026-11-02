"""Threshold alert rules over dashboard numbers.

Changelog
- v1: escalation-rate rule only.
- v2: rule objects, latency and spend rules, `evaluate` returns fired alerts.
- v2.1: min_sample guard so tiny batches do not page anyone.
"""
from __future__ import annotations

from dataclasses import dataclass

ESCALATION_RATE_MAX = 0.35
P90_LATENCY_MAX_MS = 20000.0
SPEND_PER_CONVERSATION_MAX_USD = 0.01
MIN_SAMPLE = 5


@dataclass(frozen=True)
class AlertRule:
    name: str
    metric: str          # attribute on Dashboard
    op: str              # "gt" or "lt"
    threshold: float
    severity: str = "warn"
    min_sample: int = MIN_SAMPLE

    def fires(self, dash) -> bool:
        if dash.conversations < self.min_sample:
            return False
        value = getattr(dash, self.metric)
        if self.op == "gt":
            return value > self.threshold
        if self.op == "lt":
            return value < self.threshold
        raise ValueError(f"unknown op {self.op!r}")


@dataclass(frozen=True)
class Alert:
    rule: str
    metric: str
    value: float
    threshold: float
    severity: str

    def text(self) -> str:
        return f"[{self.severity}] {self.rule}: {self.metric}={self.value:.3f} (threshold {self.threshold:.3f})"


def default_rules() -> list:
    return [
        AlertRule("escalation_rate_high", "escalation_rate", "gt", ESCALATION_RATE_MAX, "page"),
        AlertRule("latency_p90_high", "latency_p90_ms", "gt", P90_LATENCY_MAX_MS),
        AlertRule("spend_high", "spend_usd", "gt", SPEND_PER_CONVERSATION_MAX_USD * 1000, "info"),
    ]


def evaluate(dash, rules: list | None = None) -> list:
    fired = []
    for rule in rules if rules is not None else default_rules():
        if rule.fires(dash):
            fired.append(Alert(rule.name, rule.metric, float(getattr(dash, rule.metric)), rule.threshold, rule.severity))
    return fired


def format_alerts(alerts: list) -> str:
    return "\n".join(a.text() for a in alerts) if alerts else "no alerts"


class AlertState:
    """Remembers which rules already fired so a repeating batch job does not page twice for the same rule."""

    def __init__(self, cooldown_runs: int = 3):
        self.cooldown_runs = cooldown_runs
        self._last_fired: dict = {}
        self._run = 0

    def filter_new(self, fired: list) -> list:
        self._run += 1
        fresh = []
        for a in fired:
            last = self._last_fired.get(a.rule)
            if last is None or self._run - last >= self.cooldown_runs:
                fresh.append(a)
                self._last_fired[a.rule] = self._run
        return fresh
