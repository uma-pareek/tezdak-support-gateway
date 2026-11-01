"""Admin CLI over a trace directory. Run: python3 -m tezdak.ops.admin_cli <command> --traces DIR

Commands: summary, export, tail, cohorts.

Changelog
- v1: summary and tail.
- v2: export (csv or redacted traces) and cohorts.
- v2.1: --scenarios adds cohort metadata from scenario files.
"""
from __future__ import annotations

import argparse
import sys

from . import alerts, cohorts, reports
from .dashboard import build_dashboard, format_dashboard
from .records import read_trace_dir


def _build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="tezdak.ops.admin_cli")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("summary", "export", "tail", "cohorts"):
        p = sub.add_parser(name)
        p.add_argument("--traces", required=True, help="directory of *.jsonl trace files")
        p.add_argument("--scenarios", help="directory of scenario json files (adds cohort metadata)")
    sub.choices["export"].add_argument("--out", required=True, help="output file (csv) or directory (redacted)")
    sub.choices["export"].add_argument("--format", choices=("csv", "redacted"), default="csv")
    sub.choices["tail"].add_argument("-n", type=int, default=5)
    sub.choices["cohorts"].add_argument("--by", choices=cohorts.DIMENSIONS, default="language")
    return ap


def cmd_summary(records, args, out) -> int:
    print(format_dashboard(build_dashboard(records)), file=out)
    print(alerts.format_alerts(alerts.evaluate(build_dashboard(records))), file=out)
    return 0


def cmd_tail(records, args, out) -> int:
    for r in sorted(records, key=lambda r: (r.started_at, r.scenario))[-args.n:]:
        state = "escalated" if r.escalated else ("closed" if r.closed else "open")
        print(f"{r.started_at} {r.scenario} {r.intent} {state} turns={r.turns}", file=out)
    return 0


def cmd_cohorts(records, args, out) -> int:
    print(cohorts.format_cohorts(records, args.by), file=out)
    return 0


def cmd_export(records, args, out) -> int:
    if args.format == "csv":
        reports.write_csv(records, args.out)
        print(f"wrote {len(records)} rows to {args.out}", file=out)
        return 0
    from eval.trace import read_trace, write_trace
    from .retention import export_redacted_dir
    n = export_redacted_dir(args.traces, args.out, read_trace, write_trace)
    print(f"wrote {n} redacted traces to {args.out}", file=out)
    return 0


COMMANDS = {"summary": cmd_summary, "tail": cmd_tail, "cohorts": cmd_cohorts, "export": cmd_export}


def main(argv=None, out=None) -> int:
    out = out or sys.stdout
    args = _build_parser().parse_args(argv)
    try:
        records = read_trace_dir(args.traces, args.scenarios)
    except (OSError, ValueError) as exc:
        print(f"cannot read traces: {exc}", file=sys.stderr)
        return 2
    if not records:
        print("no traces found", file=sys.stderr)
        return 1
    return COMMANDS[args.command](records, args, out)


if __name__ == "__main__":
    sys.exit(main())
