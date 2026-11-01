"""Run report: report.json plus a readable report.md. Both list what happened in each chat."""
import hashlib
import json
from pathlib import Path

# Dollars per million tokens: uncached input, cached input, output.
RATE_INPUT, RATE_CACHED, RATE_OUTPUT = 0.10, 0.01, 0.50
TEXT_LIMIT = 80


def spend_usd(usage: dict) -> float:
    inp, cached = usage.get("input_tokens", 0), usage.get("cached_tokens", 0)
    out = usage.get("output_tokens", 0)
    return (max(inp - cached, 0) * RATE_INPUT + cached * RATE_CACHED + out * RATE_OUTPUT) / 1_000_000


def hash_tree(root) -> dict:
    root = Path(root)
    out = {}
    if root.is_dir():
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc":
                out[p.relative_to(root).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _previous_report(out_dir: Path):
    best = None
    for rep in out_dir.parent.glob("*/report.json"):
        if rep.parent.resolve() == out_dir.resolve():
            continue
        if best is None or rep.stat().st_mtime > best.stat().st_mtime:
            best = rep
    if best is None:
        return None, None
    return best.parent.name, json.loads(best.read_text(encoding="utf-8"))


def diff_hashes(prev: dict, cur: dict) -> list:
    return sorted(k for k in set(prev) | set(cur) if prev.get(k) != cur.get(k))


# ------------------------------------------------------------------ per-chat facts

def _brief(value):
    """A short, JSON-safe copy of a value: long text is cut, nested values become short JSON text."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return text if len(text) <= TEXT_LIMIT else text[:TEXT_LIMIT - 3] + "..."


def _brief_dict(d) -> dict:
    return {k: _brief(v) for k, v in sorted((d or {}).items())} if isinstance(d, dict) else {"value": _brief(d)}


def _ok(entry: dict) -> bool:
    return "error" not in (entry.get("result") or {})


def _amount(entry: dict) -> int:
    for src in (entry.get("result") or {}, entry.get("args") or {}):
        if isinstance(src.get("amount_inr"), int):
            return src["amount_inr"]
    return 0


def tool_calls_from_trace(events: list) -> list:
    """[{name, args, attempt, timed_out}] in call order, from the trace's tool_call and tool_timeout events."""
    calls = []
    for ev in events:
        data = ev.get("data") or {}
        if ev.get("kind") == "tool_call":
            calls.append({"name": data.get("name"), "args": _brief_dict(data.get("args")),
                          "attempt": data.get("attempt", 0), "timed_out": False})
        elif ev.get("kind") == "tool_timeout":
            for c in reversed(calls):
                if c["name"] == data.get("name") and not c["timed_out"]:
                    c["timed_out"] = True
                    break
    return calls


def ledger_facts(ledger: list) -> list:
    """The carrier's ledger, each entry shortened: seq, ts, type, awb, args, result."""
    return [{"seq": e.get("seq"), "ts": e.get("ts"), "type": e.get("type"), "awb": e.get("awb"),
             "args": _brief_dict(e.get("args")), "result": _brief_dict(e.get("result"))} for e in ledger]


def _count_types(ledger: list) -> dict:
    out: dict = {}
    for e in ledger:
        out[e.get("type")] = out.get(e.get("type"), 0) + 1
    return dict(sorted(out.items()))

