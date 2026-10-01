"""LLM client for the Responses API, plus an offline planner used when no token is configured.

Both modes return the same response shape:
    {"id", "output": [message | function_call, ...], "usage": {...}}
"""

import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.request

from .config import Config

PRICE_IN_PER_M = 0.25
PRICE_CACHED_PER_M = 0.01
PRICE_OUT_PER_M = 0.50


class LLMError(RuntimeError):
    pass


def output_text(response: dict) -> str:
    parts = []
    for item in response.get("output", []):
        if item.get("type") == "message":
            content = item.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            else:
                parts.extend(c.get("text", "") for c in content if c.get("type") == "output_text")
    return "".join(parts)


def function_calls(response: dict) -> list:
    return [i for i in response.get("output", []) if i.get("type") == "function_call"]


class LLMClient:
    def __init__(self, config: Config | None = None):
        self.config = config or Config.from_env()
        self.usage = {"input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "calls": 0}
        self._planner = _MockPlanner() if self.config.llm_mode == "mock" else None

    @property
    def mode(self) -> str:
        return self.config.llm_mode

    def respond(self, messages: list, tools: list | None = None) -> dict:
        if self._planner is not None:
            response = self._planner.respond(_replayable(messages, self.config), tools)
        else:
            body = {"input": _replayable(messages, self.config), **REQUEST_LIMITS}
            if tools:
                body["tools"] = tools
                body["tool_choice"] = "auto"
            response = self._post(body)
        self._record(response.get("usage") or {})
        return response

    def spend_usd(self) -> float:
        u = self.usage
        fresh = max(u["input_tokens"] - u["cached_tokens"], 0)
        return (fresh * PRICE_IN_PER_M + u["cached_tokens"] * PRICE_CACHED_PER_M
                + u["output_tokens"] * PRICE_OUT_PER_M) / 1_000_000

    def _record(self, usage: dict) -> None:
        details = usage.get("input_tokens_details") or {}
        self.usage["input_tokens"] += int(usage.get("input_tokens", 0))
        self.usage["cached_tokens"] += int(details.get("cached_tokens", 0))
        self.usage["output_tokens"] += int(usage.get("output_tokens", 0))
        self.usage["calls"] += 1

    def _post(self, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + self.config.llm_token}
        for attempt in range(MAX_RETRIES + 1):
            req = urllib.request.Request(self.config.llm_url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.config.llm_timeout_s) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                _wait_or_raise(exc, attempt)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise LLMError("llm request failed: %s" % exc) from exc


# ---------------------------------------------------------------- offline planner

_SLOT_ISO = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
_TODAY = re.compile(r"\b(today|aaj)\b", re.I)
_COMPLAINT = re.compile(r"nahi\s+(mila|aaya)|not\s+(received|got)|haven'?t|never|didn'?t|nobody|no\s*one", re.I)

_TEXT = {
    "status_ofd": ("Your parcel is out for delivery and should reach you today.",
                   "Aapka parcel out for delivery hai, aaj aap tak pahunch jayega."),
    "status_ndr": ("The last delivery attempt was not completed. I can book another attempt for today or tomorrow, which would you like?",
                   "Last delivery attempt complete nahi hua. Main aaj ya kal ke liye dobara attempt book kar sakta hoon, aap kaunsa chahenge?"),
    "status_transit": ("Your parcel is on its way. Latest update: {last}.",
                       "Aapka parcel raste mein hai. Latest update: {last}."),
    "status_resched": ("Your parcel already has another attempt booked. Latest update: {last}.",
                       "Aapke parcel ka dusra attempt book hai. Latest update: {last}."),
    "status_delivered": ("The parcel is marked delivered. Latest update: {last}.",
                         "Parcel delivered mark hai. Latest update: {last}."),
    "status_rto": ("This parcel is being returned to the sender.",
                   "Yeh parcel sender ko wapas bheja ja raha hai."),
    "booked": ("Done, another delivery attempt is booked for {slot}.",
               "Ho gaya, aapke parcel ka dobara attempt {slot} ke liye book ho gaya hai."),
    "booked_later": ("I could not fit today's attempt, so it is booked for {slot} instead.",
                     "Aaj ka slot nahi mil paya, isliye attempt {slot} ke liye book hua hai."),
    "pending": ("The system is slow right now. I have sent your reschedule request and you should get the parcel {slot}.",
                "System abhi slow hai. Maine aapka reschedule request bhej diya hai, parcel {slot} tak mil jayega."),
    "limit": ("This parcel has used its delivery attempts, so I have asked a senior colleague to look at it. They will contact you.",
              "Is parcel ke delivery attempts poore ho chuke hain, isliye maine senior colleague ko bheja hai. Woh aapse sampark karenge."),
    "closed_parcel": ("I am not able to book another attempt for this parcel.",
                      "Is parcel ke liye main dobara attempt book nahi kar sakta."),
    "escalated": ("I am sorry about this. I have passed your case to our support team and they will contact you.",
                  "Is takleef ke liye maafi. Maine aapka case support team ko de diya hai, woh aapse sampark karenge."),
    "already": ("Your case is already with our support team, they will contact you.",
                "Aapka case pehle se support team ke paas hai, woh aapse sampark karenge."),
    "other": ("Happy to help. Please share your tracking number or tell me what you need with your parcel.",
              "Zaroor madad karunga. Apna tracking number ya parcel ki problem bataiye."),
    "error": ("I could not look that up right now. Please try again in a few minutes.",
              "Abhi yeh check nahi ho paya. Kuch minute baad dobara try kijiye."),
}


def _approx_tokens(obj) -> int:
    return max(1, len(json.dumps(obj, default=str)) // 4)


def _kv(system: str, key: str, default: str = "") -> str:
    m = re.search(r"^%s:\s*(.+)$" % re.escape(key), system, re.M)
    return m.group(1).strip() if m else default


class _MockPlanner:
    """Rule-based stand-in for the model. Deterministic; never touches the network."""

    def __init__(self):
        self._n = 0
        self._seen_prefix = set()

    def respond(self, messages, tools):
        self._n += 1
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        last_user = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
        user_text = messages[last_user].get("content", "") if last_user >= 0 else ""
        calls = {}
        outputs = {}
        for m in messages[last_user + 1:]:
            if m.get("type") == "function_call":
                calls[m["call_id"]] = m
            elif m.get("type") == "function_call_output":
                outputs[m["call_id"]] = json.loads(m["output"])
        done = {calls[c]["name"]: outputs[c] for c in outputs if c in calls}
        item = self._plan(system, user_text, done)
        response = {"id": "resp_mock_%d" % self._n, "object": "response", "status": "completed", "output": [item]}
        prefix = hashlib.sha1(system.encode("utf-8")).hexdigest()
        cached = _approx_tokens(system) if prefix in self._seen_prefix else 0
        self._seen_prefix.add(prefix)
        response["usage"] = {
            "input_tokens": _approx_tokens(messages) + _approx_tokens(tools or []),
            "input_tokens_details": {"cached_tokens": cached},
            "output_tokens": _approx_tokens(item),
        }
        return response

    def _call(self, name, **args):
        return {"type": "function_call", "call_id": "call_mock_%d" % self._n, "name": name,
                "arguments": json.dumps(args)}

    @staticmethod
    def _say(key, lang, eta="none", **kw):
        en, hi = _TEXT[key]
        text = (hi if lang == "hinglish" else en).format(**kw)
        return {"type": "message", "role": "assistant",
                "content": [{"type": "output_text", "text": "%s\nETA: %s" % (text, eta)}]}

    def _plan(self, system, user_text, done):
        intent = _kv(system, "Intent", "other")
        awb = _kv(system, "AWB")
        lang = _kv(system, "Reply language", "english")
        today = _kv(system, "Today")
        limit = int(_kv(system, "Attempt limit", "3"))
        escalated = _kv(system, "Already escalated", "no") == "yes"
        ship = done.get("get_shipment")

        if not awb or intent == "other":
            return self._say("other", lang)
        if ship is not None and ship.get("error"):
            return self._say("error", lang)
        if intent in ("ndr_complaint", "not_received_after_delivered"):
            return self._plan_complaint(awb, lang, done, ship, escalated, limit)
        if ship is None:
            return self._call("get_shipment", awb=awb)
        if intent == "wismo" and ship.get("status") == "DELIVERED" and _COMPLAINT.search(user_text):
            return self._plan_complaint(awb, lang, done, ship, escalated, limit)
        if intent == "reschedule_request":
            return self._plan_reschedule(awb, lang, user_text, today, done, ship, limit)
        return self._plan_wismo(awb, lang, done, ship)

    def _plan_complaint(self, awb, lang, done, ship, escalated, limit):
        if escalated:
            return self._say("already", lang)
        if ship is None:
            return self._call("get_shipment", awb=awb)
        if "escalate" not in done:
            kind = "hub_override" if int(ship.get("attempts_used", 0)) >= limit else "agent_review"
            return self._call("escalate", awb=awb, reason="customer complaint about delivery", kind=kind)
        return self._say("escalated", lang)

    def _plan_wismo(self, awb, lang, done, ship):
        status = ship.get("status")
        if status in ("NDR", "RESCHEDULED", "IN_TRANSIT", "DELIVERED") and "get_scans" not in done:
            return self._call("get_scans", awb=awb)
        scans = done.get("get_scans")
        last = scans[-1]["status_text"] if isinstance(scans, list) and scans else "no scan yet"
        if status == "NDR":
            return self._say("status_ndr", lang)
        eta = "none"
        if status == "OUT_FOR_DELIVERY":
            msg, eta = "status_ofd", "today"
        elif status == "RESCHEDULED":
            msg = "status_resched"
        elif status == "DELIVERED":
            msg = "status_delivered"
        elif status == "RTO_INITIATED":
            msg = "status_rto"
        else:
            msg = "status_transit"
        if "close" not in done:
            return self._call("close", awb=awb, resolution="answered status question")
        return self._say(msg, lang, eta=eta, last=last)

    def _plan_reschedule(self, awb, lang, user_text, today, done, ship, limit):
        if ship.get("status") in ("DELIVERED", "RTO_INITIATED"):
            return self._say("closed_parcel", lang)
        if int(ship.get("attempts_used", 0)) >= limit:
            if "escalate" not in done:
                return self._call("escalate", awb=awb, reason="attempt limit reached, customer wants another attempt",
                                  kind="hub_override")
            return self._say("limit", lang)
        iso = _SLOT_ISO.search(user_text)
        slot = iso.group(1) if iso else "today" if _TODAY.search(user_text) else "tomorrow"
        if "reschedule" not in done:
            return self._call("reschedule", awb=awb, slot=slot)
        res = done["reschedule"]
        if res.get("error"):
            if "close" not in done:
                return self._call("close", awb=awb, resolution="reschedule requested, carrier pending")
            return self._say("pending", lang, eta=slot, slot=slot)
        booked = str(res.get("slot_booked") or slot)
        if "close" not in done:
            return self._call("close", awb=awb, resolution="rescheduled for %s" % booked)
        later = slot == "today" and booked not in ("today", today)
        return self._say("booked_later" if later else "booked", lang, eta=booked, slot=booked)


# ---------------------------------------------------------------- request and retry settings

REQUEST_LIMITS = {"reasoning": {"effort": "low"}, "max_output_tokens": 1200}
RETRY_STATUS = (429, 502, 503)
MAX_RETRIES = 3
RETRY_AFTER_DEFAULT_S = 3.0
RETRY_AFTER_CAP_S = 20.0


def _replayable(messages: list, config: Config) -> list:
    """The input items to send. With LLM_REPLAY_REASONING=0, earlier reasoning items are left out."""
    if config.llm_replay_reasoning:
        return messages
    return [m for m in messages if m.get("type") != "reasoning"]


def _retry_delay(retry_after) -> float:
    """Seconds to wait before a retry: the Retry-After value (default 3) plus a little jitter, capped at 20."""
    try:
        base = float(retry_after)
    except (TypeError, ValueError):
        base = RETRY_AFTER_DEFAULT_S
    return min(max(base, 0.0) + random.uniform(0, 0.5), RETRY_AFTER_CAP_S)


def _wait_or_raise(exc: urllib.error.HTTPError, attempt: int) -> None:
    """Sleep before the next try when the status is a busy or rate-limit reply; otherwise raise LLMError."""
    detail = exc.read()[:300].decode("utf-8", "replace")
    if exc.code not in RETRY_STATUS:
        raise LLMError("llm http %s: %s" % (exc.code, detail)) from exc
    if attempt >= MAX_RETRIES:
        raise LLMError("llm http %s, still failing after %d retries (rate limit or endpoint busy): %s"
                       % (exc.code, MAX_RETRIES, detail)) from exc
    time.sleep(_retry_delay(exc.headers.get("Retry-After") if exc.headers else None))
