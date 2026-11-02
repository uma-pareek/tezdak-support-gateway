"""Daily and weekly report text plus CSV export.

Changelog
- v1: daily text report.
- v2: weekly roll-up (ISO week), CSV export of per-conversation rows.
- v2.2: `format_report` kept for old callers, now delegates to `daily_report`.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime

from .dashboard import build_dashboard, format_dashboard

CSV_COLUMNS = ("scenario", "started_at", "channel", "language", "payment_mode", "pincode", "tier", "intent",
               "closed", "escalated", "turns", "input_tokens", "cached_tokens", "output_tokens", "llm_calls")


def record_date(rec) -> date | None:
    try:
        return datetime.fromisoformat(rec.started_at).date()
    except (TypeError, ValueError):
        return None


def records_on(records: list, day: date) -> list:
    return [r for r in records if record_date(r) == day]


def iso_week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def daily_report(records: list, day: date) -> str:
    subset = records_on(records, day)
    head = f"Daily support report for {day.isoformat()}"
    if not subset:
        return head + "\nNo conversations."
    return head + "\n" + format_dashboard(build_dashboard(subset))


def weekly_report(records: list, week: str) -> str:
    """`week` is an ISO week key such as 2026-W45."""
    subset = [r for r in records if (d := record_date(r)) and iso_week_key(d) == week]
    head = f"Weekly support report for {week}"
    if not subset:
        return head + "\nNo conversations."
    days: dict = {}
    for r in subset:
        days.setdefault(record_date(r), []).append(r)
    lines = [head, format_dashboard(build_dashboard(subset)), "by day:"]
    for day in sorted(days):
        dash = build_dashboard(days[day])
        lines.append(f"  {day.isoformat()} n={dash.conversations} resolved={100 * dash.resolved_rate:.1f}% "
                     f"escalated={100 * dash.escalation_rate:.1f}%")
    return "\n".join(lines)


def format_report(records: list) -> str:
    """Deprecated: report for the most recent day present in the records."""
    days = [d for d in (record_date(r) for r in records) if d]
    if not days:
        return "No conversations."
    return daily_report(records, max(days))


def export_csv(records: list) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in records:
        writer.writerow([getattr(r, c) for c in CSV_COLUMNS])
    return buf.getvalue()


def write_csv(records: list, path) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(export_csv(records))


def markdown_report(records: list, title: str = "Support report") -> str:
    from .dashboard import to_markdown
    return to_markdown(build_dashboard(records), title)


def by_day_rows(records: list) -> list:
    """Rows (date, conversations, resolved_rate, escalation_rate) in date order; undated records are skipped."""
    days: dict = {}
    for r in records:
        d = record_date(r)
        if d:
            days.setdefault(d, []).append(r)
    rows = []
    for d in sorted(days):
        dash = build_dashboard(days[d])
        rows.append((d.isoformat(), dash.conversations, dash.resolved_rate, dash.escalation_rate))
    return rows
