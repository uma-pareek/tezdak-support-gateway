"""v2 intent taxonomy and the LLM classification path.

Changelog
- v2.0  taxonomy trimmed from ~30 rule intents to 18 coarser intents.
- v2.1  JSON-only prompt, tolerant parser (accepts fenced JSON and bare labels).
- v2.2  confidence floor; below it we hand back to the rules.
Without an `llm` the function is a thin wrapper over the fallback rules, mapped into the v2 taxonomy.
"""

import json
import re
from dataclasses import dataclass, field

from .entities import Entities, extract
from .language import detect_language
from .rules_v1 import classify_v1

INTENTS_V2 = (
    "wismo", "not_received_after_delivered", "reschedule_request", "ndr_complaint",
    "address_change", "cancel_order", "refund_status", "feedback", "rider_behaviour",
    "item_problem", "payment_issue", "human_agent", "small_talk", "delivery_instructions",
    "return_request", "otp_issue", "abuse", "other",
)

# v1 label -> v2 label
V1_TO_V2 = {
    "greeting": "small_talk", "thanks": "small_talk", "goodbye": "small_talk",
    "damaged_item": "item_problem", "wrong_item": "item_problem", "missing_item": "item_problem",
    "cod_query": "payment_issue", "invoice_request": "other", "change_phone": "address_change",
    "price_query": "other", "serviceability": "other", "hold_at_hub": "reschedule_request",
    "contact_rider": "rider_behaviour",
}
CONFIDENCE_FLOOR = 0.5

INTENT_HINTS_V2 = {
    "wismo": "asks where the parcel is or when it will come",
    "not_received_after_delivered": "app says delivered but customer has not got it",
    "reschedule_request": "wants another delivery attempt or a specific day or slot",
    "ndr_complaint": "says the rider did not come, did not call, or a delivery attempt is wrong",
    "address_change": "wants address, pincode or phone number changed",
    "cancel_order": "wants the order cancelled or stopped",
    "refund_status": "asks about refund, wallet credit or goodwill money",
    "feedback": "praise, rating or general suggestion",
    "rider_behaviour": "rider rude, asked for money, or customer wants rider contact",
    "item_problem": "damaged, wrong or missing item",
    "payment_issue": "double charge, failed payment, cash on delivery questions",
    "human_agent": "asks for a human or a manager",
    "small_talk": "greeting, thanks, goodbye",
    "delivery_instructions": "leave with guard, call before coming, and similar",
    "return_request": "return, exchange or replacement",
    "otp_issue": "delivery OTP problems",
    "abuse": "insults or threats",
    "other": "none of the above",
}


@dataclass
class IntentResultV2:
    intent: str
    confidence: float
    source: str                     # "llm" | "rules" | "llm_rejected"
    reason: str = ""
    language: str = "english"
    entities: Entities = field(default_factory=Entities)

    def to_dict(self) -> dict:
        return {
            "intent": self.intent, "confidence": self.confidence, "source": self.source,
            "reason": self.reason, "language": self.language, "entities": self.entities.to_dict(),
        }


def build_system_prompt() -> str:
    lines = [
        "You classify one customer message sent to a parcel delivery support bot.",
        "Customers write English or Hinglish (Hindi in roman letters).",
        'Reply with JSON only: {"intent": <label>, "confidence": <0..1>, "reason": <short>}.',
        "Labels:",
    ]
    lines += [f"- {k}: {INTENT_HINTS_V2[k]}" for k in INTENTS_V2]
    lines.append("If unsure pick other with low confidence. Never invent labels.")
    return "\n".join(lines)


def build_messages(text: str, shipment_status: str | None = None) -> list:
    user = f"shipment_status: {shipment_status or 'unknown'}\nmessage: {text}"
    return [
        {"role": "system", "content": build_system_prompt()},
        {"role": "user", "content": user},
    ]


_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


def parse_llm_output(raw: str) -> tuple | None:
    """Return (intent, confidence, reason) or None when the output is unusable."""
    raw = (raw or "").strip()
    if not raw:
        return None
    m = _JSON_BLOCK.search(raw)
    if m:
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            obj = None
        if isinstance(obj, dict) and obj.get("intent") in INTENTS_V2:
            try:
                conf = float(obj.get("confidence", 0.6))
            except (TypeError, ValueError):
                conf = 0.6
            return obj["intent"], max(0.0, min(1.0, conf)), str(obj.get("reason", ""))[:200]
    bare = raw.strip("`\"' \n.").lower()
    if bare in INTENTS_V2:
        return bare, 0.6, "bare label"
    return None


def map_v1_label(label: str) -> str:
    if label in INTENTS_V2:
        return label
    return V1_TO_V2.get(label, "other")


def _call_llm(llm, messages: list) -> str:
    # lazy import keeps rules-only callers free of the llm module
    from tezdak.llm import output_text

    return output_text(llm.respond(messages))


def classify_v2(text, llm=None, fallback=classify_v1, shipment_status=None, now=None) -> IntentResultV2:
    """Structured classification. Rules answer when `llm` is None, fails or is unsure."""
    lang = detect_language(text).label
    ents = extract(text, now)
    fb_label, fb_score = fallback(text, shipment_status)
    fb_intent = map_v1_label(fb_label)
    if llm is None:
        return IntentResultV2(fb_intent, fb_score, "rules", "no llm", lang, ents)
    try:
        parsed = parse_llm_output(_call_llm(llm, build_messages(text, shipment_status)))
    except Exception as exc:  # noqa: BLE001  llm errors must never break a customer turn
        return IntentResultV2(fb_intent, fb_score, "rules", f"llm error: {type(exc).__name__}", lang, ents)
    if parsed is None:
        return IntentResultV2(fb_intent, fb_score, "llm_rejected", "unparseable output", lang, ents)
    intent, conf, reason = parsed
    if conf < CONFIDENCE_FLOOR:
        return IntentResultV2(fb_intent, fb_score, "llm_rejected", f"low confidence {conf:.2f}", lang, ents)
    return IntentResultV2(intent, conf, "llm", reason, lang, ents)
