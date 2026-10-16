"""Single entry point for intent classification.

`classify(text, shipment_status=None, now=None) -> NluResult`.
For engine v1 the five base intents are exactly what `tezdak.router.classify` returns.
Extra intents (address_change, cancel_order, refund_status, ...) only appear when the base router
says "other", so they never collide with the base five.
"""

from dataclasses import dataclass, field

from tezdak import router

from . import flags
from .entities import Entities, extract
from .intents_v2 import classify_v2
from .language import detect_language
from .rules_v1 import BASE_INTENTS, best_extra
from .shadow import run_shadow


@dataclass
class NluResult:
    intent: str
    language: str
    entities: Entities = field(default_factory=Entities)
    engine: str = "v1"
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {"intent": self.intent, "language": self.language, "entities": self.entities.to_dict(),
                "engine": self.engine, "confidence": self.confidence}


def classify_v1_engine(text: str, shipment_status: str | None = None) -> tuple:
    base = router.classify(text, shipment_status)
    if base != "other":
        return base, 0.85
    extra, score = best_extra(text)
    if extra in BASE_INTENTS:  # defensive: the weighted table never emits these today
        return "other", 0.0
    return extra, score


def classify(text, shipment_status=None, now=None, llm=None, engine=None) -> NluResult:
    engine = engine or flags.engine_name()
    lang = detect_language(text).label
    ents = extract(text, now)
    if engine == "v2":
        r = classify_v2(text, llm=llm, shipment_status=shipment_status, now=now)
        return NluResult(r.intent, lang, ents, "v2", r.confidence)
    intent, score = classify_v1_engine(text, shipment_status)
    if engine == "shadow":
        run_shadow(text, shipment_status, llm=llm, now=now)
    return NluResult(intent, lang, ents, "shadow" if engine == "shadow" else "v1", score)
