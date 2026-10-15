"""Tiny offline evaluation helpers for comparing classifiers on labelled text.

Changelog
- v1  accuracy and confusion counts.
- v2  per-intent precision/recall, text report. Used by whoever tunes the rules by hand.
"""

from collections import Counter, defaultdict


def evaluate(classifier, labelled: list) -> dict:
    """`classifier(text) -> intent`; `labelled` is [(text, gold_intent)]."""
    confusion: Counter = Counter()
    for text, gold in labelled:
        confusion[(gold, classifier(text))] += 1
    total = sum(confusion.values())
    correct = sum(n for (g, p), n in confusion.items() if g == p)
    labels = sorted({g for g, _ in confusion} | {p for _, p in confusion})
    per = {}
    for lab in labels:
        tp = confusion[(lab, lab)]
        fp = sum(n for (g, p), n in confusion.items() if p == lab and g != lab)
        fn = sum(n for (g, p), n in confusion.items() if g == lab and p != lab)
        per[lab] = {
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "support": tp + fn,
        }
    return {
        "total": total, "accuracy": round(correct / total, 3) if total else None,
        "per_intent": per, "confusion": {f"{g}->{p}": n for (g, p), n in confusion.items() if g != p},
    }


def compare(a, b, texts: list) -> dict:
    """Where two classifiers disagree: {text: (a_label, b_label)}."""
    return {t: (a(t), b(t)) for t in texts if a(t) != b(t)}


def group_by_intent(texts: list, classifier) -> dict:
    groups = defaultdict(list)
    for t in texts:
        groups[classifier(t)].append(t)
    return dict(groups)


def report(result: dict) -> str:
    lines = [f"total={result['total']} accuracy={result['accuracy']}"]
    for lab, m in result["per_intent"].items():
        lines.append(f"{lab:32s} p={m['precision']} r={m['recall']} n={m['support']}")
    for k, n in sorted(result["confusion"].items(), key=lambda kv: -kv[1])[:10]:
        lines.append(f"  miss {k}: {n}")
    return "\n".join(lines)
