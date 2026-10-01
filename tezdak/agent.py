"""Support agent: routes a customer message, runs the tool loop, returns the reply.

Changelog
  0.1  First version, status questions and reschedules only.

TODO: handle more than one AWB per chat.
TODO: keep conversation state outside the process.
"""

import json
import os
import re
from dataclasses import dataclass, field
from datetime import timedelta

from . import router
from .config import Config
from .llm import function_calls, output_text
from .policies import Policies
from .tools import ToolBox

# Features that overlap the base intents stay off until their tool names are reconciled with the base tools.
FEATURES_OFF_BY_DEFAULT = ("wismo_detail", "slot_picker", "not_received_helper")

AWB_RE = re.compile(r"\bTZ\d{6,}\b")
ETA_LINE = re.compile(r"^ETA:\s*(\S+)\s*$", re.I | re.M)
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FALLBACK_REPLY = "Sorry, I am having trouble with this one. A colleague will follow up with you."

SYSTEM_PROMPT = """You are Tezdak's customer support assistant for parcel deliveries.
Be brief and polite. Reply in English; use simple Hinglish when the customer writes Hinglish.
Only use the tools provided. Never invent delivery dates.
{policy}

AWB: {awb}
Today: {today}
Intent: {intent}
Reply language: {language}
Attempt limit: {limit}
Already escalated: {escalated}

{hint}

End every reply with one line `ETA: <today|tomorrow|YYYY-MM-DD|none>` stating the delivery date you promised, or none."""

INTENT_HINTS = {
    "wismo": "Check the shipment (and scans if needed) and tell the customer where the parcel is.",
    "reschedule_request": "Book another attempt for the slot the customer asked for, unless the parcel is out of attempts.",
    "ndr_complaint": "Complaints about a missed or failed attempt go to a human: check the shipment, then escalate.",
    "not_received_after_delivered": "Delivered-but-not-received cases go to a human: check the shipment, then escalate.",
    "other": "Answer briefly and ask for the tracking number if you need it.",
}


@dataclass
class Conversation:
    messages: list
    awb: str | None = None

    @classmethod
    def coerce(cls, obj) -> "Conversation":
        if isinstance(obj, Conversation):
            return obj
        if isinstance(obj, dict):
            return cls(messages=list(obj.get("messages", [])), awb=obj.get("awb"))
        return cls(messages=list(obj))


@dataclass
class AgentTurn:
    reply: str
    commitments: list = field(default_factory=list)
    intent: str = "other"
    tool_calls: list = field(default_factory=list)
    model_calls: int = 0
    escalated: bool = False
    closed: bool = False


def eta_commitments(reply_text: str, today) -> tuple[str, list]:
    """Split the trailing ETA line off the reply and turn it into commitments."""
    m = None
    for m in ETA_LINE.finditer(reply_text):
        pass
    if m is None:
        return reply_text.strip(), []
    body = (reply_text[:m.start()] + reply_text[m.end():]).strip()
    value = m.group(1).strip().lower()
    if value in ("none", "n/a", "-"):
        return body, []
    if ISO_DATE.match(value) and today is not None:
        if value == today.date().isoformat():
            value = "today"
        elif value == (today.date() + timedelta(days=1)).isoformat():
            value = "tomorrow"
    elif value not in ("today", "tomorrow") and not ISO_DATE.match(value):
        return body, []
    return body, [{"type": "eta", "value": value}]


class SupportAgent:
    def __init__(self, llm, carrier, policies=None, config=None, metrics=None, on_event=None, backend=None):
        self.llm = llm
        self.carrier = carrier
        self.policies = policies or Policies()
        self.config = config or Config()
        self.metrics = metrics
        self.on_event = on_event
        self.tools = ToolBox(carrier, self.policies, on_event=self._emit)
        self._escalated = set()
        self.backend = backend
        self.planner = self._build_planner() if backend is not None else None

    def _build_planner(self):
        from .features.config import FeatureConfig
        from .features.planner import FeaturePlanner
        cfg = FeatureConfig.from_env()
        if not os.environ.get("TEZDAK_FEATURES_DISABLED"):
            cfg.disabled = tuple(FEATURES_OFF_BY_DEFAULT)
        return FeaturePlanner(config=cfg)

    def _classify(self, text, today):
        """Base keyword router unless TEZDAK_NLU_ENGINE picks the newer NLU package."""
        if os.environ.get("TEZDAK_NLU_ENGINE"):
            from .nlu.facade import classify as nlu_classify
            res = nlu_classify(text, now=today)
            return res.intent, res.language
        return router.classify(text), router.detect_language(text)

    def _feature_ctx(self, awb, text, intent, language, today):
        from .features.base import FeatureContext
        return FeatureContext(awb=awb, user_text=text, intent=intent, language=language,
                              carrier=self.carrier, backend=self.backend, policies=self.policies, now=today)

    def _emit(self, kind, data):
        if self.on_event:
            self.on_event(kind, data)

    def tools_names(self):
        return {t["name"] for t in self.tools.specs}

    def _find_awb(self, conv: Conversation):
        if conv.awb:
            return conv.awb
        for m in reversed(conv.messages):
            found = AWB_RE.search(m.get("content", "") or "")
            if found:
                conv.awb = found.group(0)
                return conv.awb
        return None

    def _system_prompt(self, awb, intent, language, today, extra_hint=""):
        hint = INTENT_HINTS.get(intent, INTENT_HINTS["other"])
        if extra_hint:
            hint = hint + "\n" + extra_hint
        if os.environ.get("TEZDAK_PROMPT_VERSION"):
            from .prompts.loader import render_system_prompt
            return render_system_prompt(
                awb=awb or "unknown", today=today.date().isoformat() if today else "unknown",
                intent=intent, language=language, limit=self.policies.max_attempts(),
                escalated="yes" if awb in self._escalated else "no", hint=hint,
                policy=self.policies.prompt_text())
        return SYSTEM_PROMPT.format(
            policy=self.policies.prompt_text(),
            awb=awb or "unknown",
            today=today.date().isoformat() if today else "unknown",
            intent=intent,
            language=language,
            limit=self.policies.max_attempts(),
            escalated="yes" if awb in self._escalated else "no",
            hint=hint,
        )

    def handle(self, conversation) -> AgentTurn:
        conv = Conversation.coerce(conversation)
        user_text = next((m["content"] for m in reversed(conv.messages) if m.get("role") == "user"), "")
        awb = self._find_awb(conv)
        today = getattr(self.carrier, "now", None)
        intent, language = self._classify(user_text, today)

        ctx = extra_specs = None
        extra_hint = ""
        if self.planner is not None:
            ctx = self._feature_ctx(awb, user_text, intent, language, today)
            extra_specs = self.planner.specs(ctx)
            extra_hint = self.planner.hint_block(ctx)

        items = [{"role": "system", "content": self._system_prompt(awb, intent, language, today, extra_hint)}]
        items += [{"role": m["role"], "content": m["content"]} for m in conv.messages
                  if m.get("role") in ("user", "assistant")]

        turn = AgentTurn(reply=FALLBACK_REPLY, intent=intent)
        for _ in range(self.config.max_model_calls):
            response = self.llm.respond(items, tools=self.tools.specs + (extra_specs or []))
            turn.model_calls += 1
            calls = function_calls(response)
            if not calls:
                body, commitments = eta_commitments(output_text(response), today)
                turn.reply, turn.commitments = body or FALLBACK_REPLY, commitments
                break
            items.extend(i for i in response["output"] if i.get("type") in ("function_call", "message", "reasoning"))
            for call in calls:
                args = json.loads(call.get("arguments") or "{}")
                if ctx is not None and call["name"] not in self.tools_names():
                    self._emit("feature_call", {"name": call["name"], "args": args})
                    result = self.planner.dispatch(call["name"], args, ctx)
                    self._emit("feature_result", {"name": call["name"], "result": result})
                else:
                    result = self.tools.call(call["name"], args)
                failed = isinstance(result, dict) and "error" in result
                turn.tool_calls.append({"name": call["name"], "args": args, "result": result})
                if not failed and call["name"] == "escalate":
                    turn.escalated = True
                    if awb:
                        self._escalated.add(awb)
                if not failed and call["name"] == "close":
                    turn.closed = True
                items.append({"type": "function_call_output", "call_id": call["call_id"],
                              "output": json.dumps(result, default=str)})
        if self.metrics is not None:
            self.metrics.record(turn)
        return turn
