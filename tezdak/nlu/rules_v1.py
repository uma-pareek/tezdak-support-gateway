"""The OLD rules-based classifier (v1). About 30 intents, a few hundred patterns.

Changelog
- 2023.4  five base intents lifted from the first keyword router (same regexes, same order).
- 2023.8  added greeting/thanks/goodbye so the bot stops saying "other" to "hi".
- 2024.1  address_change, cancel_order, refund_status after the seller escalations.
- 2024.3  Hinglish spellings widened. Scores became a sum of weights (capped at 1.0).
- 2024.6  rider_behaviour, otp_issue, hold_at_hub. Priority table split from the rule table.

The first block below is the base-intent ladder. It runs on the RAW text and is order sensitive;
do not reorder without checking the parity tests. The second block is the weighted table that
runs on normalized text.
"""

import re
from dataclasses import dataclass

from .lexicon import expand
from .normalizer import normalize_text

BASE_INTENTS = ("wismo", "not_received_after_delivered", "reschedule_request", "ndr_complaint", "other")

# ---- base ladder (raw text) -------------------------------------------------------------
_NDR = re.compile(
    r"rider\s+(aaya|aayi|nahi\s+aaya|never)|nobody\s+(came|visited)|no\s*one\s+(came|visited)"
    r"|(didn'?t|did\s+not|never)\s+(come|visit|show)|failed\s+(delivery|attempt)|\bndr\b"
    r"|not\s+attempted|attempt\s+(nahi|not)|koi\s+nahi\s+aaya|call\s+nahi\s+(kiya|aaya)"
    r"|delivery\s+boy\s+(nahi|never)|fake\s+attempt",
    re.I,
)
_NOT_RECEIVED = re.compile(
    r"(not|n'?t)\s+(received|got|get)|haven'?t\s+(received|got)|never\s+(received|got)"
    r"|nahi\s+(mila|aaya|pahuncha)|nahin\s+mila|never\s+arrived",
    re.I,
)
_DELIVERED = re.compile(
    r"deliver(ed|y\s+ho\s+gaya)|deliver\s+ho\s+gaya|marked\s+delivered|delivered\s+dikha", re.I
)
_RESCHEDULE = re.compile(
    r"re-?schedule|re-?attempt|deliver\s+(it\s+)?(today|tomorrow|tmrw|on)"
    r"|(aaj|kal|parso)\s+(deliver|bhej|de\s+do|karo)"
    r"|deliver\s+kar(o|na|dena)|another\s+(attempt|try)|try\s+again|slot|baad\s+mein\s+deliver"
    r"|phir\s+se\s+deliver|\b(kal|aaj|tomorrow|tmrw)\b.*\b(bhejo|bhej\s+do|de\s+do|karna|karo)\b",
    re.I,
)
_WISMO = re.compile(
    r"where\s+is|where'?s|\bstatus\b|track|kahan|kidhar|when\s+(will|is|does)|\bkab\b|eta\b"
    r"|update\s+on|kitne\s+din|any\s+update",
    re.I,
)


def classify_base(text: str, shipment_status: str | None = None) -> str:
    t = text or ""
    if _NOT_RECEIVED.search(t) and (_DELIVERED.search(t) or shipment_status == "DELIVERED"):
        return "not_received_after_delivered"
    if _NDR.search(t):
        return "ndr_complaint"
    if _RESCHEDULE.search(t):
        return "reschedule_request"
    if _WISMO.search(t) or _NOT_RECEIVED.search(t):
        return "wismo"
    return "other"


# ---- weighted table (normalized text) ---------------------------------------------------
@dataclass(frozen=True)
class Rule:
    intent: str
    pattern: re.Pattern
    weight: float = 0.5
    note: str = ""


def _r(intent: str, weight: float, *patterns: str) -> list:
    return [Rule(intent, re.compile(p, re.I), weight) for p in patterns]


_RULES: list = []
_RULES += _r("greeting", 0.9, r"^(hi+|hello+|hey+|namaste|namaskar|hii+)\b", r"^good\s+(morning|afternoon|evening)", r"^(hola|yo)\b")
_RULES += _r("thanks", 0.9, r"\bthank(s| you)?\b", r"\bthnx\b", r"\bshukriya\b", r"\bdhanyavaad\b", r"\bthanku\b")
_RULES += _r("goodbye", 0.9, r"^(bye|goodbye|ok bye|tata)\b", r"\bsee you\b", r"\bchalo bye\b")
_RULES += _r(
    "address_change", 0.7,
    r"\b(change|update|edit|correct|badal|badalna|badlo|badal do)\b.{0,25}\b(address|pata|pincode|location)\b",
    r"\b(address|pata)\b.{0,25}\b(change|wrong|galat|badal|update|incorrect)\b",
    r"\bwrong address\b", r"\bgalat (address|pata)\b", r"\bnew address\b", r"\bnaya (address|pata)\b",
    r"\bdeliver to (another|different|my office|my home)\b", r"\boffice (ka|pe|par) (address|bhejo)\b",
    r"\bflat (number|no)\b.{0,15}\b(change|wrong|galat)\b", r"\blandmark\b.{0,20}\b(add|change)\b",
)
_RULES += _r(
    "cancel_order", 0.8,
    r"\bcancel\b", r"\bcancellation\b", r"\border (nahi chahiye|cancel)\b", r"\bdon'?t want (it|this|the order)\b",
    r"\b(order|parcel|ye|yeh|isko) nahi chahiye\b", r"\bstop (the )?(order|shipment|delivery)\b", r"\border (ko )?(rok|roko|band)\b",
    r"\bchanged my mind\b", r"\bmann badal\b",
)
_RULES += _r(
    "refund_status", 0.8,
    r"\brefund\b", r"\bmoney back\b", r"\bpaisa (wapas|kab|nahi aaya)\b", r"\bpaise (wapas|kab|nahi aaye)\b",
    r"\bcredit(ed)? (to|in) (my )?(wallet|account|bank)\b", r"\bwallet\b", r"\bpayout\b", r"\bupi (refund|payment)\b",
    r"\bamount (wapas|return|back)\b", r"\bgoodwill\b", r"\bcompensation\b", r"\bmuaavza\b",
)
_RULES += _r(
    "feedback", 0.7,
    r"\bfeedback\b", r"\brate (the |your )?(rider|service|delivery|app)\b", r"\b(good|great|excellent|best|bad|worst|poor) (service|rider|delivery|experience)\b",
    r"\bsuggestion\b", r"\b[1-5] ?(star|stars)\b", r"\breview\b", r"\bbahut (accha|achha|badhiya)\b", r"\bkhush\b",
    r"\bbura (experience|service)\b", r"\bnaraaz\b",
)
_RULES += _r(
    "human_agent", 0.9,
    r"\b(talk|speak|connect|baat)\b.{0,20}\b(human|agent|person|executive|manager|insaan)\b",
    r"\bhuman\b", r"\breal person\b", r"\bcustomer (care|support) (number|executive)\b", r"\bcall me\b",
    r"\bmanager\b", r"\bsenior\b", r"\bsupervisor\b", r"\bagent se baat\b", r"\bexecutive se\b", r"\bcomplaint (karni|karna|darj)\b",
)
_RULES += _r(
    "rider_behaviour", 0.8,
    r"\brider\b.{0,25}\b(rude|abuse|abused|misbehav\w*|shout\w*|threat\w*|bad|behaviour|behavior|bdtameez|badtameez)\b",
    r"\b(delivery boy|rider)\b.{0,15}\b(gaali|chilla\w*|badtameezi|zabardasti|paise maang\w*)\b",
    r"\bmisbehav\w*\b", r"\bharass\w*\b", r"\basked for (extra )?(money|tip|cash)\b", r"\btip maang\w*\b",
)
_RULES += _r(
    "damaged_item", 0.9,
    r"\bdamag\w*\b", r"\bbroken\b", r"\bcrack\w*\b", r"\btoot\w*\b", r"\bphut\w*\b", r"\btorn\b", r"\bleak\w*\b",
    r"\bopened (box|package|parcel)\b", r"\bbox (khula|open|tampered)\b", r"\btamper\w*\b", r"\bcrushed\b",
)
_RULES += _r(
    "wrong_item", 0.9,
    r"\bwrong (item|product|size|colou?r|parcel)\b", r"\bgalat (item|product|size|saman|parcel)\b",
    r"\bdifferent (item|product)\b", r"\bnot what i ordered\b", r"\bye (nahi|maine nahi) (order|mangaya)\b",
    r"\bkuch aur (aaya|mila|bheja)\b", r"\bsomeone else'?s (parcel|order)\b",
)
_RULES += _r(
    "missing_item", 0.8,
    r"\bmissing (item|product|part|piece)\b", r"\bitem (missing|nahi)\b", r"\bonly (one|1|two|2) (item|piece)\b",
    r"\bbox (empty|khali)\b", r"\bempty (box|parcel|package)\b", r"\bkhali (box|dabba)\b", r"\bone item (is )?(missing|short)\b",
    r"\bsaman kam\b",
)
_RULES += _r(
    "payment_issue", 0.8,
    r"\bpayment (failed|stuck|pending|deducted|issue|problem)\b", r"\bdouble (charged|payment|charge)\b",
    r"\bcharged twice\b", r"\bpaisa (kat|kate|cut)\b", r"\bamount deducted\b", r"\bpayment nahi\b",
    r"\bextra (charge|charged|money)\b", r"\bovercharg\w*\b", r"\bupi (failed|pending)\b", r"\btransaction (failed|id)\b",
)
_RULES += _r(
    "cod_query", 0.7,
    r"\bcod\b", r"\bcash on delivery\b", r"\bcash (de|dena|pay|payment)\b", r"\bchange (hai|nahi hai|milega)\b",
    r"\bonline pay\w*\b.{0,15}\b(cod|delivery)\b", r"\bconvert (to )?prepaid\b", r"\bpay online instead\b",
    r"\bcash nahi hai\b", r"\bqr (code|scan)\b",
)
_RULES += _r(
    "otp_issue", 0.8,
    r"\botp\b", r"\bone time password\b", r"\bverification code\b", r"\bcode (nahi|not) (aaya|received|mila)\b",
    r"\b(didn'?t|did not|nahi) (get|receive|mila).{0,10}otp\b", r"\bwrong otp\b", r"\botp (galat|wrong|expired|not working)\b",
)
_RULES += _r(
    "invoice_request", 0.8,
    r"\binvoice\b", r"\bbill\b", r"\breceipt\b", r"\bgst\b", r"\btax (invoice|bill)\b", r"\bpaperwork\b",
    r"\bproof of (delivery|purchase)\b", r"\bpod copy\b",
)
_RULES += _r(
    "change_phone", 0.8,
    r"\b(change|update|new|naya|badal)\b.{0,15}\b(phone|mobile|number|contact)\b", r"\balternate (number|phone|contact)\b",
    r"\bcall (on|this|my other) number\b", r"\bdusra (number|phone)\b", r"\bwrong (phone|number)\b",
    r"\bnumber (galat|change|badal)\b", r"\bwhatsapp number\b",
)
_RULES += _r(
    "delivery_instructions", 0.7,
    r"\bleave (it |the parcel )?(with|at)\b", r"\bsecurity (guard|gate|desk)\b", r"\bguard (ko|ke paas)\b",
    r"\bcall before\b", r"\bring the bell\b", r"\bdon'?t ring\b", r"\bbell (mat|nahi)\b", r"\bneighbou?r\b",
    r"\bpehle call\b", r"\b(gate|lobby|reception) (pe|par|at)\b", r"\bdelivery instruction\w*\b", r"\bdoor ke bahar\b",
)
_RULES += _r(
    "return_request", 0.8,
    r"\breturn\b", r"\bexchange\b", r"\breplace\w*\b", r"\bwapas (karna|kar do|karo|bhejna)\b", r"\bpickup (my|the|this) (item|order)\b",
    r"\breturn policy\b", r"\bsize (issue|chota|bada|doesn'?t fit)\b", r"\bdoesn'?t fit\b", r"\bbadalna hai\b",
)
_RULES += _r(
    "price_query", 0.6,
    r"\b(delivery|shipping|courier) (charge|charges|fee|cost|price)\b", r"\bhow much (does|will|is|for)\b",
    r"\bkitna (charge|lagega|paisa|rate)\b", r"\bcharges kitne\b", r"\brate (kya|list)\b", r"\bpricing\b", r"\btariff\b",
)
_RULES += _r(
    "serviceability", 0.8,
    r"\bpincode\b.{0,25}\b(serviceable|service|deliver|available|covered)\b", r"\b(do you|can you|kya aap) deliver (to|in|at|karte)\b",
    r"\bservice available\b", r"\bkya (mere|hamare) (area|pincode|city)\b", r"\bserviceable\b", r"\bdeliver\w* to (my )?(pincode|area|city)\b",
)
_RULES += _r(
    "hold_at_hub", 0.8,
    r"\b(pick ?up|collect)\b.{0,20}\b(hub|office|branch|warehouse|myself)\b", r"\bhub (se|pe|par) (le|collect|pickup)\b",
    r"\bhold (the )?(parcel|package|shipment)\b", r"\bkeep (it )?at (the )?hub\b", r"\bkhud (aa|le|collect)\b",
    r"\bself pick ?up\b", r"\bhub (address|location|timing)\b",
)
_RULES += _r(
    "contact_rider", 0.8,
    r"\brider (ka|ke) (number|phone|contact)\b", r"\b(rider|delivery boy)'?s? (number|phone|contact)\b",
    r"\bcall the rider\b", r"\bspeak to (the )?rider\b", r"\brider se baat\b", r"\bdelivery boy (ka|ke) number\b",
    r"\bgive me (the )?rider\b",
)
_RULES += _r(
    "abuse", 0.95,
    r"\b(idiot|stupid|useless|fraud|scam|cheat\w*|bastard|bakwas|chor|fraudster|nalayak)\b", r"\bf+u+c+k\w*\b",
    r"\bsala\b", r"\bsaale\b", r"\bbewakoof\b", r"\bgadha\b", r"\bharami\b", r"\bpathetic\b", r"\bshame on\b",
)

# higher number wins a tie; abuse and human_agent must beat softer topical matches
PRIORITY = {
    "abuse": 100, "human_agent": 90, "otp_issue": 80, "damaged_item": 78, "wrong_item": 77, "missing_item": 76,
    "payment_issue": 75, "cancel_order": 70, "address_change": 68, "change_phone": 66, "hold_at_hub": 64,
    "contact_rider": 62, "rider_behaviour": 60, "return_request": 58, "refund_status": 56, "cod_query": 54,
    "invoice_request": 52, "serviceability": 50, "price_query": 48, "delivery_instructions": 46,
    "feedback": 44, "greeting": 20, "thanks": 18, "goodbye": 16,
}
EXTRA_INTENTS = tuple(sorted(PRIORITY))
ALL_INTENTS = BASE_INTENTS + EXTRA_INTENTS
LOW_CONFIDENCE = 0.4


def rule_count() -> int:
    return len(_RULES)


def score_table(text: str) -> dict:
    """Return {intent: summed weight (<=1.0)} for weighted-table matches on normalized text."""
    t = normalize_text(expand(text))
    scores: dict = {}
    for rule in _RULES:
        if rule.pattern.search(t):
            scores[rule.intent] = min(1.0, scores.get(rule.intent, 0.0) + rule.weight)
    return scores


def best_extra(text: str) -> tuple:
    scores = score_table(text)
    if not scores:
        return "other", 0.0
    intent = max(scores, key=lambda i: (scores[i], PRIORITY.get(i, 0)))
    return (intent, round(scores[intent], 2)) if scores[intent] >= LOW_CONFIDENCE else ("other", 0.0)


def classify_v1(text: str, shipment_status: str | None = None) -> tuple:
    """Return (intent, score). Base ladder first; the weighted table only runs on base 'other'."""
    base = classify_base(text, shipment_status)
    if base != "other":
        return base, 0.85 if base != "wismo" else 0.7
    return best_extra(text)


def classify_v1_intent(text: str, shipment_status: str | None = None) -> str:
    return classify_v1(text, shipment_status)[0]


# deprecated: the pre-2024.3 API returned only the label
classify_label = classify_v1_intent
