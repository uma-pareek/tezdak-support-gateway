"""Hand-built trace events and (optionally) real traces from the eval runner, for the ops tests."""
import importlib
import os
import sys
import tempfile
from pathlib import Path

CANDIDATE = Path(__file__).resolve().parent.parent
if str(CANDIDATE) not in sys.path:
    sys.path.insert(0, str(CANDIDATE))
PRIVATE = str(CANDIDATE.parent / "private")
DEV = CANDIDATE / "tests" / "fixtures" / "dev6"


def sim_available() -> bool:
    if PRIVATE not in sys.path:
        sys.path.insert(0, PRIVATE)
    try:
        importlib.import_module("carrier_sim")
        importlib.import_module("tezdak.agent")
    except ImportError:
        return False
    return True


def ev(scenario, seq, t, kind, data):
    return {"scenario": scenario, "seq": seq, "t": t, "kind": kind, "data": data}


def make_events(scenario="s-1", text="Rider aaya hi nahi, kab milega?", closed=False, escalated=False,
                day="2026-11-02", awb="TZ4829301", tokens=(1000, 200, 100), reply_after_s=2, extra_ledger=()):
    t0 = f"{day}T12:00:00+05:30"
    t1 = f"{day}T12:00:{reply_after_s:02d}+05:30"
    events = [
        ev(scenario, 0, t0, "customer_msg", {"text": text}),
        ev(scenario, 1, t0, "tool_call", {"name": "get_shipment", "args": {"awb": awb}, "attempt": 0}),
        ev(scenario, 2, t0, "tool_result", {"name": "get_shipment", "result": {"status": "NDR"}}),
        ev(scenario, 3, t1, "agent_msg", {"text": f"Aapka parcel {awb} kal aayega.", "commitments": []}),
    ]
    ledger = list(extra_ledger)
    if escalated:
        ledger.append({"type": "escalated", "awb": awb})
    if closed:
        ledger.append({"type": "closed", "awb": awb})
    for entry in ledger:
        events.append(ev(scenario, len(events), t1, "ledger", entry))
    inp, cached, out = tokens
    events.append(ev(scenario, len(events), t1, "llm_usage",
                     {"input_tokens": inp, "cached_tokens": cached, "output_tokens": out, "calls": 2, "spend_usd": 0.0}))
    return events


def write_fixture_dir(root, specs):
    """specs: list of dicts passed to make_events. Returns the directory path."""
    from eval.trace import write_trace
    for spec in specs:
        write_trace(make_events(**spec), Path(root) / f"{spec['scenario']}.jsonl")
    return Path(root)


def run_real_traces(out_dir):
    """Run the real eval runner over data/dev with the mock LLM. Returns the traces directory."""
    old = os.environ.get("LLM_MODE")
    os.environ["LLM_MODE"] = "mock"
    try:
        from eval.run_eval import run_dir
        run_dir(DEV, Path(out_dir))
    finally:
        if old is None:
            os.environ.pop("LLM_MODE", None)
        else:
            os.environ["LLM_MODE"] = old
    return Path(out_dir) / "traces"
