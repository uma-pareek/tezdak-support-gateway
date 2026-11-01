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


def scenario_facts(scenario_id, events, ledger, outcome, usage, error=None) -> dict:
    """What happened in one chat. Counts and records only."""
    refunds = [{"amount_inr": _amount(e), "kind": (e.get("args") or {}).get("kind"),
                "mode": (e.get("result") or {}).get("mode")}
               for e in ledger if e.get("type") == "refund_issued" and _ok(e)]
    calls = tool_calls_from_trace(events)
    return {
        "id": scenario_id,
        "customer_turns": sum(1 for ev in events if ev.get("kind") == "customer_msg"),
        "agent_turns": sum(1 for ev in events if ev.get("kind") == "agent_msg"),
        "tool_calls": calls,
        "ledger": ledger_facts(ledger),
        "ledger_by_type": _count_types(ledger),
        "attempts_used": (outcome or {}).get("attempts_used"),
        "bookings": sum(1 for e in ledger if e.get("type") == "reschedule_applied"
                       and (e.get("result") or {}).get("status") == "ok"),
        "refunds": refunds,
        "refunds_paid_inr": sum(r["amount_inr"] for r in refunds),
        "escalated": any(e.get("type") == "escalated" and _ok(e) for e in ledger),
        "closed": any(e.get("type") == "closed" and _ok(e) for e in ledger),
        "llm": {**usage, "spend_usd": spend_usd(usage)},
        "error": error,
    }


def build_report(name, facts, usage, tezdak_dir, out_dir) -> dict:
    hashes = hash_tree(tezdak_dir)
    prev_name, prev = _previous_report(Path(out_dir))
    return {
        "name": name,
        "scenarios": facts,
        "llm": {**usage, "spend_usd": spend_usd(usage)},
        "errors": {f["id"]: f["error"] for f in facts if f["error"]},
        "tezdak_hashes": hashes,
        "previous_run": prev_name,
        "diff_vs_previous": None if prev is None else diff_hashes(prev.get("tezdak_hashes", {}), hashes),
    }


# ------------------------------------------------------------------ text

def _types_text(by_type: dict) -> str:
    return ", ".join(f"{k} x{v}" for k, v in by_type.items()) or "none"


def _yn(flag) -> str:
    return "yes" if flag else "no"


def scenario_line(f: dict) -> str:
    return (f"{f['id']}: {f['customer_turns']} customer turns, {len(f['tool_calls'])} tool calls, "
            f"ledger: {_types_text(f['ledger_by_type'])}; attempts used {f['attempts_used']}, "
            f"bookings {f['bookings']}, refunds {len(f['refunds'])} (Rs {f['refunds_paid_inr']}), "
            f"escalated {_yn(f['escalated'])}, closed {_yn(f['closed'])}; LLM calls {f['llm'].get('calls', 0)}, "
            f"spend ${f['llm']['spend_usd']:.4f}" + (f"; error: {f['error']}" if f["error"] else ""))


def llm_line(rep: dict) -> str:
    llm = rep["llm"]
    return (f"LLM calls {llm.get('calls', 0)}, input tokens {llm.get('input_tokens', 0)}, "
            f"cached {llm.get('cached_tokens', 0)}, output {llm.get('output_tokens', 0)}, spend ${llm['spend_usd']:.4f}")


def render_markdown(rep: dict) -> str:
    llm = rep["llm"]
    lines = [
        f"# Run report: {rep['name']}", "",
        f"- LLM calls: {llm.get('calls', 0)}, input tokens: {llm.get('input_tokens', 0)}, "
        f"cached: {llm.get('cached_tokens', 0)}, output: {llm.get('output_tokens', 0)}, spend: ${llm['spend_usd']:.4f}",
        "", "## Chats", "",
        "| id | customer turns | tool calls | ledger | attempts used | bookings | refunds (Rs) | escalated | closed | LLM calls |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for f in rep["scenarios"]:
        lines.append(f"| {f['id']} | {f['customer_turns']} | {len(f['tool_calls'])} | {_types_text(f['ledger_by_type'])} | "
                     f"{f['attempts_used']} | {f['bookings']} | {f['refunds_paid_inr']} | {_yn(f['escalated'])} | "
                     f"{_yn(f['closed'])} | {f['llm'].get('calls', 0)} |")
    lines += ["", "## Change since previous run", ""]
    if rep["diff_vs_previous"] is None:
        lines.append("No previous run found.")
    elif not rep["diff_vs_previous"]:
        lines.append(f"No file in tezdak/ changed since `{rep['previous_run']}`.")
    else:
        lines.append(f"Files in tezdak/ changed since `{rep['previous_run']}`:")
        lines += [f"- {f}" for f in rep["diff_vs_previous"]]
    if rep["errors"]:
        lines += ["", "## Errors", ""] + [f"- {k}: {v}" for k, v in rep["errors"].items()]
    return "\n".join(lines) + "\n"


def write_report(out_dir, rep: dict) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(rep, indent=2, sort_keys=True), encoding="utf-8")
    (out_dir / "report.md").write_text(render_markdown(rep), encoding="utf-8")
