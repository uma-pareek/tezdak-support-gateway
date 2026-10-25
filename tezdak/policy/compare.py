"""Diff two policy generations for one shipment. Used from notebooks and the ops console."""

from .eligibility import refund_eligibility
from .loader import load_policy

FIELDS = ("allowed", "reason", "window_days", "limit_inr", "needs_human")


def compare_policies(shipment, claim, a="v1", b="v2") -> dict:
    pa = load_policy(a) if isinstance(a, str) else a
    pb = load_policy(b) if isinstance(b, str) else b
    da = refund_eligibility(shipment, claim, pa)
    db = refund_eligibility(shipment, claim, pb)
    diff = {}
    for f in FIELDS:
        va, vb = getattr(da, f), getattr(db, f)
        if va != vb:
            diff[f] = (va, vb)
    return {"a": pa.name, "b": pb.name, "decision_a": da, "decision_b": db, "diff": diff}


def compare_all(shipment, claim, names=("v1", "v2", "v3")) -> dict:
    return {n: refund_eligibility(shipment, claim, load_policy(n)) for n in names}


def format_diff(result: dict) -> str:
    if not result["diff"]:
        return f"{result['a']} and {result['b']} agree"
    lines = [f"{result['a']} vs {result['b']}"]
    for field, (va, vb) in result["diff"].items():
        lines.append(f"  {field}: {va} -> {vb}")
    return "\n".join(lines)
