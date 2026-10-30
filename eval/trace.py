"""JSONL trace schema: one object per event."""
import json
from pathlib import Path

KINDS = ("customer_msg", "agent_msg", "tool_call", "tool_result", "tool_timeout", "ledger", "llm_usage",
         "feature_call", "feature_result", "session_start")
FIELDS = ("scenario", "seq", "t", "kind", "data")


def validate_event(ev: dict) -> None:
    """Raise ValueError if the event does not match the trace schema."""
    if not isinstance(ev, dict) or set(ev) != set(FIELDS):
        raise ValueError(f"event must have exactly the fields {FIELDS}: {ev!r}")
    if not isinstance(ev["scenario"], str) or not isinstance(ev["t"], str):
        raise ValueError("scenario and t must be strings")
    if not isinstance(ev["seq"], int) or isinstance(ev["seq"], bool):
        raise ValueError("seq must be an int")
    if ev["kind"] not in KINDS:
        raise ValueError(f"unknown kind {ev['kind']!r}")
    if not isinstance(ev["data"], dict):
        raise ValueError("data must be an object")
    if ev["kind"] in ("tool_call", "tool_timeout", "feature_call"):
        for key in (("name", "args") if ev["kind"] == "feature_call" else ("name", "args", "attempt")):
            if key not in ev["data"]:
                raise ValueError(f"{ev['kind']} data needs {key!r}")


class Trace:
    def __init__(self, scenario_id: str, clock):
        self.scenario_id = scenario_id
        self._clock = clock
        self.events: list[dict] = []

    def add(self, kind: str, data: dict) -> dict:
        data = json.loads(json.dumps(data, default=str))
        ev = {"scenario": self.scenario_id, "seq": len(self.events), "t": self._clock(), "kind": kind, "data": data}
        validate_event(ev)
        self.events.append(ev)
        return ev


def write_trace(events: list[dict], path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")


def read_trace(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]
    for ev in events:
        validate_event(ev)
    return events
