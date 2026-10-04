"""Run scenarios against an agent. CLI: python3 -m eval.run_eval --dir data/dev --out runs/<name>"""
import argparse
import inspect
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .customers import ScriptedCustomer
from .report import build_report, scenario_facts, scenario_line, spend_usd, llm_line, write_report
from .trace import Trace, write_trace

WRITE_TOOLS = ("reschedule", "open_rider_dispute", "create_refund", "escalate", "close")
TOOLS = ("get_shipment", "get_scans") + WRITE_TOOLS
USAGE_KEYS = ("input_tokens", "cached_tokens", "output_tokens", "calls")


@dataclass
class RunResult:
    scenario_id: str
    trace: list
    ledger: list
    outcome: dict
    commitments: list
    facts: dict
    llm_usage: dict
    transcript: list = field(default_factory=list)
    error: str | None = None


class TracingCarrier:
    """Wraps a carrier and records every tool call, result and timeout in the trace."""

    def __init__(self, sim, trace: Trace):
        self._sim = sim
        self._trace = trace
        self._timeouts: dict = {}

    def __getattr__(self, name):
        attr = getattr(self._sim, name)
        if name not in TOOLS:
            return attr
        sig = inspect.signature(attr)

        def call(*a, **kw):
            args = dict(sig.bind(*a, **kw).arguments)
            key = (name, json.dumps(args, sort_keys=True, default=str))
            attempt = self._timeouts.get(key, 0)
            self._trace.add("tool_call", {"name": name, "args": args, "attempt": attempt})
            try:
                result = attr(*a, **kw)
            except Exception as exc:
                if type(exc).__name__ != "CarrierTimeout":
                    raise
                self._timeouts[key] = attempt + 1
                self._trace.add("tool_timeout", {"name": name, "args": args, "attempt": attempt,
                                                 "timeout_s": args.get("timeout_s")})
                raise
            self._timeouts.pop(key, None)
            self._trace.add("tool_result", {"name": name, "result": result})
            return result
        return call


def default_carrier_factory(scenario):
    from carrier_sim import CarrierSim  # the vendor package: PYTHONPATH=vendor:.
    return CarrierSim(scenario)


class _AwbAdapter:
    """Hands the shipment id to tezdak's SupportAgent, whose chat input carries it beside the messages."""

    def __init__(self, agent, awb):
        self._agent = agent
        self._awb = awb
        self.llm = agent.llm

    def handle(self, conversation):
        return self._agent.handle({"messages": conversation, "awb": self._awb})


def default_agent_factory(carrier):
    from tezdak.agent import SupportAgent
    from tezdak.carrier_client import CarrierClient
    from tezdak.llm import LLMClient
    backend = None
    scenario = getattr(carrier, "scenario", None)
    if scenario is not None:
        from tezdak.backend.facade import Backend
        backend = Backend.from_scenario(scenario)
    trace = getattr(carrier, "_trace", None)

    def on_event(kind, data):
        if trace is not None and kind in ("feature_call", "feature_result"):
            trace.add(kind, data)

    return _AwbAdapter(SupportAgent(LLMClient(), CarrierClient(carrier), backend=backend, on_event=on_event),
                       getattr(carrier, "awb", None))


def scripted_customer_factory(scenario):
    c = scenario["customer"]
    return ScriptedCustomer(c["card"], c["script"])


def _field(turn, *names):
    for n in names:
        v = turn.get(n) if isinstance(turn, dict) else getattr(turn, n, None)
        if v is not None:
            return v
    return None


def _usage(agent):
    u = getattr(getattr(agent, "llm", None), "usage", None)
    return {k: int(u.get(k, 0)) for k in USAGE_KEYS} if isinstance(u, dict) else {k: 0 for k in USAGE_KEYS}


def run_scenario(scenario, agent_factory, customer_factory=None, carrier_factory=None) -> RunResult:
    sim = (carrier_factory or default_carrier_factory)(scenario)
    trace = Trace(scenario["id"], clock=lambda: sim.now.isoformat())
    carrier = TracingCarrier(sim, trace)
    carrier.awb = scenario["world"]["shipment"]["awb"]
    carrier.scenario = scenario
    trace.add("session_start", {"channel": scenario.get("channel", "chat"), "scenario": scenario["id"]})
    customer = (customer_factory or scripted_customer_factory)(scenario)
    agent = agent_factory(carrier)
    before = _usage(agent)

    conversation: list = []
    commitments: list = []
    error = None
    try:
        msg = customer.opening()
        while msg is not None:
            conversation.append({"role": "user", "content": msg})
            trace.add("customer_msg", {"text": msg})
            turn = agent.handle(conversation)
            text = _field(turn, "text", "reply", "message") or (turn if isinstance(turn, str) else "")
            commitments.extend(_field(turn, "commitments") or [])
            conversation.append({"role": "assistant", "content": text})
            trace.add("agent_msg", {"text": text, "commitments": _field(turn, "commitments") or []})
            msg = customer.reply(text)
    except Exception as exc:  # recorded in the trace and the report, never swallowed
        error = f"{type(exc).__name__}: {exc}"

    ledger = sim.ledger()
    outcome = sim.outcome() if hasattr(sim, "outcome") else {}
    for entry in ledger:
        trace.add("ledger", entry)
    after = _usage(agent)
    usage = {k: after[k] - before[k] for k in USAGE_KEYS}
    trace.add("llm_usage", {**usage, "spend_usd": spend_usd(usage), **({"error": error} if error else {})})
    facts = scenario_facts(scenario["id"], trace.events, ledger, outcome, usage, error)
    return RunResult(scenario["id"], trace.events, ledger, outcome, commitments, facts, usage, conversation, error)


def load_scenarios(directory) -> list:
    files = sorted(Path(directory).glob("*.json"))
    return [json.loads(p.read_text(encoding="utf-8")) for p in files]


def run_dir(directory, out, agent_factory=None, customer_factory=None, carrier_factory=None) -> dict:
    out = Path(out)
    results = [run_scenario(s, agent_factory or default_agent_factory, customer_factory, carrier_factory)
               for s in load_scenarios(directory)]
    for r in results:
        write_trace(r.trace, out / "traces" / f"{r.scenario_id}.jsonl")
    usage = {k: sum(r.llm_usage[k] for r in results) for k in USAGE_KEYS}
    tezdak_dir = Path(__file__).resolve().parent.parent / "tezdak"
    rep = build_report(out.name, [r.facts for r in results], usage, tezdak_dir, out)
    write_report(out, rep)
    return rep


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="eval.run_eval")
    ap.add_argument("--dir", required=True, help="folder of scenario JSON files")
    ap.add_argument("--out", required=True, help="run folder, e.g. runs/my-run")
    args = ap.parse_args(argv)
    try:
        rep = run_dir(args.dir, args.out)
    except ImportError as exc:
        print(f"import failed: {exc}. Set PYTHONPATH=vendor:. so carrier_sim and tezdak are importable.",
              file=sys.stderr)
        return 2
    for f in rep["scenarios"]:
        print(scenario_line(f))
    print(llm_line(rep))
    print(f"Report: {Path(args.out) / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
