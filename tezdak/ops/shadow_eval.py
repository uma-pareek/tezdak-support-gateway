"""Compare two trace directories on action counts.

Changelog
- v1: per-scenario action counts.
- v2: aggregate delta and a text diff; tolerant of scenarios present on one side only.
"""
from __future__ import annotations

from .records import WRITE_TOOLS, read_trace_dir


def action_counts(records: list) -> dict:
    counts: dict = {}
    for r in records:
        for typ, n in r.action_counts.items():
            counts[typ] = counts.get(typ, 0) + n
    return counts


def per_scenario(records: list) -> dict:
    return {r.scenario: dict(r.action_counts) for r in records}


def tool_counts(records: list, writes_only: bool = False) -> dict:
    counts: dict = {}
    for r in records:
        for name, n in r.tool_counts.items():
            if writes_only and name not in WRITE_TOOLS:
                continue
            counts[name] = counts.get(name, 0) + n
    return counts


def compare(base: list, other: list) -> dict:
    a, b = per_scenario(base), per_scenario(other)
    changed = {}
    for sid in sorted(set(a) & set(b)):
        if a[sid] != b[sid]:
            changed[sid] = {"base": a[sid], "other": b[sid]}
    ca, cb = action_counts(base), action_counts(other)
    delta = {k: cb.get(k, 0) - ca.get(k, 0) for k in sorted(set(ca) | set(cb))}
    return {
        "only_in_base": sorted(set(a) - set(b)),
        "only_in_other": sorted(set(b) - set(a)),
        "changed": changed,
        "delta": {k: v for k, v in delta.items() if v},
        "base_total": ca,
        "other_total": cb,
    }


def compare_dirs(base_dir, other_dir) -> dict:
    return compare(read_trace_dir(base_dir), read_trace_dir(other_dir))


def format_comparison(result: dict) -> str:
    lines = [f"scenarios only in base: {result['only_in_base'] or 'none'}",
             f"scenarios only in other: {result['only_in_other'] or 'none'}",
             f"scenarios with different actions: {len(result['changed'])}"]
    for sid, diff in result["changed"].items():
        lines.append(f"  {sid}: {diff['base']} -> {diff['other']}")
    lines.append("action delta (other - base): " + (str(result["delta"]) if result["delta"] else "none"))
    return "\n".join(lines)
