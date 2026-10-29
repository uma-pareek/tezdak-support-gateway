"""Reviewer sample selection from conversation records.

Changelog
- v1: random sample with a seed.
- v2: stratified sample per intent, forced inclusion of escalated conversations.
- v2.1: `pick_for_review` returns scenario ids only (reviewer tool joins on id).
"""
from __future__ import annotations

import random


def random_sample(records: list, n: int, seed: int = 7) -> list:
    if n >= len(records):
        return list(records)
    return random.Random(seed).sample(records, n)


def stratified_sample(records: list, per_intent: int, seed: int = 7) -> list:
    rng = random.Random(seed)
    groups: dict = {}
    for r in records:
        groups.setdefault(r.intent, []).append(r)
    chosen = []
    for intent in sorted(groups):
        group = sorted(groups[intent], key=lambda r: r.scenario)
        chosen.extend(group if len(group) <= per_intent else rng.sample(group, per_intent))
    return chosen


def escalated_first(records: list, n: int, seed: int = 7) -> list:
    esc = sorted((r for r in records if r.escalated), key=lambda r: r.scenario)
    rest = [r for r in records if not r.escalated]
    picked = esc[:n]
    if len(picked) < n:
        picked += random_sample(rest, n - len(picked), seed)
    return picked


def long_conversations(records: list, min_turns: int = 6) -> list:
    return [r for r in records if r.turns >= min_turns]


def pick_for_review(records: list, n: int, seed: int = 7, include_long: bool = True) -> list:
    """Scenario ids for human review: escalated first, long ones next, then random fill. No duplicates."""
    order = list(escalated_first(records, n, seed))
    if include_long:
        order += long_conversations(records)
    order += random_sample(records, len(records), seed)
    seen, ids = set(), []
    for r in order:
        if r.scenario not in seen:
            seen.add(r.scenario)
            ids.append(r.scenario)
        if len(ids) >= n:
            break
    return ids


def review_sheet_csv(records: list, ids: list) -> str:
    """CSV the reviewers fill in: scenario, intent, first customer text, empty verdict column."""
    import csv
    import io
    by_id = {r.scenario: r for r in records}
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["scenario", "intent", "first_text", "verdict"])
    for sid in ids:
        r = by_id.get(sid)
        if r:
            w.writerow([r.scenario, r.intent, r.first_text, ""])
    return buf.getvalue()
