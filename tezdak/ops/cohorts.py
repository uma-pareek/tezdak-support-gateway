"""Group conversation records into cohorts and build a dashboard per cohort.

Changelog
- v1: channel and language.
- v2: payment mode, pincode tier.
- v2.1: `pincode_tier` falls back to a first-digit guess when the record has no tier (legacy traces).
"""
from __future__ import annotations

from .dashboard import build_dashboard

DIMENSIONS = ("channel", "language", "payment_mode", "pincode_tier")
_METRO_PREFIXES = ("11", "40", "56", "60", "70", "50")  # delhi, mumbai, bengaluru, chennai, kolkata, hyderabad


def pincode_tier(rec) -> str:
    if rec.tier and rec.tier != "unknown":
        return rec.tier
    if rec.pincode and rec.pincode[:2] in _METRO_PREFIXES:
        return "metro"
    return "unknown" if not rec.pincode else "tier2"


def cohort_key(rec, dimension: str) -> str:
    if dimension == "pincode_tier":
        return pincode_tier(rec)
    if dimension in DIMENSIONS:
        return getattr(rec, dimension) or "unknown"
    raise ValueError(f"unknown cohort dimension {dimension!r}; choose from {DIMENSIONS}")


def group_by(records: list, dimension: str) -> dict:
    groups: dict = {}
    for r in records:
        groups.setdefault(cohort_key(r, dimension), []).append(r)
    return dict(sorted(groups.items()))


def cohort_dashboards(records: list, dimension: str) -> dict:
    return {k: build_dashboard(v) for k, v in group_by(records, dimension).items()}


def cohort_table(records: list, dimension: str) -> list:
    """Rows of (cohort, n, resolved_rate, escalation_rate, spend_usd) for printing or CSV."""
    rows = []
    for key, dash in cohort_dashboards(records, dimension).items():
        rows.append((key, dash.conversations, dash.resolved_rate, dash.escalation_rate, dash.spend_usd))
    return rows


def format_cohorts(records: list, dimension: str) -> str:
    lines = [f"cohorts by {dimension}"]
    for key, n, res, esc, spend in cohort_table(records, dimension):
        lines.append(f"  {key:<14} n={n:<4} resolved={100 * res:5.1f}% escalated={100 * esc:5.1f}% spend=${spend:.4f}")
    return "\n".join(lines)
