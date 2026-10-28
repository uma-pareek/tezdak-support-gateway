"""Conversation records built from eval-schema trace files.

Changelog
- v1: ConversationRecord + trace reader.
- v2: metadata merge from scenario files (payment mode, pincode, tier, language).
- v3: JSONL reader/writer for flattened records (`records_v1` schema).
- v3.1: `iter_trace_dir` helper; `load_records` kept as a deprecated alias.
"""
from __future__ import annotations

import json
import warnings
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

try:  # the eval package sits next to tezdak/ in the candidate folder
    from eval.trace import read_trace, write_trace
except ImportError:  # pragma: no cover - only when run outside the candidate folder
    read_trace = write_trace = None

from tezdak.router import classify as _router_classify, detect_language as _detect_language

WRITE_TOOLS = ("reschedule", "open_rider_dispute", "create_refund", "escalate", "close")
DEFAULT_CHANNEL = "chat"
RECORD_SCHEMA = "records_v1"


@dataclass
class ConversationRecord:
    scenario: str
    channel: str = DEFAULT_CHANNEL
    language: str = "unknown"
    payment_mode: str = "unknown"
    pincode: str = ""
    tier: str = "unknown"
    intent: str = "other"
    awb: str = ""
    phone: str = ""
    closed: bool = False
    escalated: bool = False
    turns: int = 0
    started_at: str = ""
    first_text: str = ""
    latencies_ms: list = field(default_factory=list)
    input_tokens: int = 0
    cached_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    tool_counts: dict = field(default_factory=dict)
    action_counts: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["schema"] = RECORD_SCHEMA
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ConversationRecord":
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in names})

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def _parse_ts(value: str):
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def metadata_from_scenario(scenario: dict) -> dict:
    """Pull cohort fields out of a scenario file. Only shipment-level and customer-card fields are used."""
    world = scenario.get("world") or {}
    ship = world.get("shipment") or {}
    card = (scenario.get("customer") or {}).get("card") or {}
    return {
        "channel": scenario.get("channel") or DEFAULT_CHANNEL,
        "language": card.get("language"),
        "payment_mode": ship.get("payment_mode"),
        "pincode": ship.get("pincode"),
        "tier": ship.get("tier"),
        "phone": ship.get("phone"),
        "awb": ship.get("awb"),
    }


def load_metadata_dir(directory) -> dict:
    """Map scenario id -> metadata for every *.json in `directory`."""
    out = {}
    for p in sorted(Path(directory).glob("*.json")):
        try:
            sc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(sc, dict) and sc.get("id"):
            out[sc["id"]] = metadata_from_scenario(sc)
    return out


def record_from_events(events: list, metadata: dict | None = None) -> ConversationRecord:
    """Fold one scenario's trace events into a ConversationRecord."""
    if not events:
        raise ValueError("cannot build a record from an empty trace")
    meta = {k: v for k, v in (metadata or {}).items() if v not in (None, "")}
    rec = ConversationRecord(scenario=events[0]["scenario"], started_at=events[0]["t"])
    last_customer_ts = None
    for ev in events:
        kind, data = ev["kind"], ev["data"]
        if kind == "customer_msg":
            last_customer_ts = _parse_ts(ev["t"])
            if not rec.first_text:
                rec.first_text = str(data.get("text", ""))
        elif kind == "agent_msg":
            rec.turns += 1
            end = _parse_ts(ev["t"])
            if last_customer_ts and end:
                rec.latencies_ms.append(max(int((end - last_customer_ts).total_seconds() * 1000), 0))
            last_customer_ts = None
        elif kind == "tool_call":
            name = data.get("name", "?")
            rec.tool_counts[name] = rec.tool_counts.get(name, 0) + 1
            if not rec.awb and isinstance(data.get("args"), dict):
                rec.awb = str(data["args"].get("awb", "") or "")
        elif kind == "ledger":
            typ = data.get("type")
            if typ == "closed":
                rec.closed = True
            elif typ == "escalated":
                rec.escalated = True
            rec.action_counts[typ] = rec.action_counts.get(typ, 0) + 1
            rec.awb = rec.awb or str(data.get("awb", ""))
        elif kind == "llm_usage":
            rec.input_tokens += int(data.get("input_tokens", 0))
            rec.cached_tokens += int(data.get("cached_tokens", 0))
            rec.output_tokens += int(data.get("output_tokens", 0))
            rec.llm_calls += int(data.get("calls", 0))
    rec.intent = meta.pop("intent", None) or _router_classify(rec.first_text)
    rec.language = meta.pop("language", None) or _detect_language(rec.first_text)
    for key in ("channel", "payment_mode", "pincode", "tier", "phone", "awb"):
        if key in meta:
            setattr(rec, key, str(meta.pop(key)))
    rec.metadata = meta
    return rec


def iter_trace_dir(directory):
    """Yield (path, events) for every *.jsonl file under `directory` (recursive, sorted)."""
    root = Path(directory)
    for path in sorted(root.rglob("*.jsonl")):
        yield path, read_trace(path)


def read_trace_dir(directory, metadata_dir=None) -> list:
    """Build records from a trace directory. `metadata_dir` is an optional folder of scenario files."""
    meta = load_metadata_dir(metadata_dir) if metadata_dir else {}
    records = []
    for _path, events in iter_trace_dir(directory):
        if events:
            records.append(record_from_events(events, meta.get(events[0]["scenario"])))
    return records


def load_records(directory, metadata_dir=None) -> list:
    """Deprecated alias of read_trace_dir."""
    warnings.warn("load_records is deprecated, use read_trace_dir", DeprecationWarning, stacklevel=2)
    return read_trace_dir(directory, metadata_dir)


def write_records_jsonl(records: list, path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")


def read_records_jsonl(path) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            d = json.loads(line)
            if d.get("schema") != RECORD_SCHEMA:
                raise ValueError(f"{path}:{n}: unexpected record schema {d.get('schema')!r}")
            out.append(ConversationRecord.from_dict(d))
    return out


def write_events(events: list, path) -> None:
    """Thin wrapper so callers of this module do not need the eval package for writing traces."""
    write_trace(events, path)


def filter_records(records: list, *, intent: str | None = None, channel: str | None = None,
                   since: str | None = None, until: str | None = None, escalated: bool | None = None) -> list:
    """Filter by exact fields and an ISO date window (`since` inclusive, `until` exclusive, date strings)."""
    out = []
    for r in records:
        if intent is not None and r.intent != intent:
            continue
        if channel is not None and r.channel != channel:
            continue
        if escalated is not None and r.escalated != escalated:
            continue
        day = r.started_at[:10]
        if since and day < since:
            continue
        if until and day >= until:
            continue
        out.append(r)
    return out


def merge_record_sets(*sets) -> list:
    """Combine several lists of records; later sets win on scenario id collisions."""
    merged: dict = {}
    for records in sets:
        for r in records:
            merged[r.scenario] = r
    return list(merged.values())


def scenario_ids(records: list) -> list:
    return sorted(r.scenario for r in records)
