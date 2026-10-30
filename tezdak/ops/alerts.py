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
