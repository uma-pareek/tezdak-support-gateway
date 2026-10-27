"""Tool layer: JSON-schema function tools the model can call, backed by the carrier client."""

from .carrier_client import CARRIER_TIMEOUT_S, CarrierTimeout
from .policies import Policies

TOOL_TIMEOUT_S = CARRIER_TIMEOUT_S
TOOL_RETRIES = 2


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": properties, "required": required},
    }


_AWB = {"type": "string", "description": "Shipment AWB, for example TZ4829301"}

TOOL_SPECS = [
    _tool("get_shipment", "Current shipment status, attempts used, payment mode and amount.",
          {"awb": _AWB}, ["awb"]),
    _tool("get_scans", "Scan history for the shipment, oldest first.", {"awb": _AWB}, ["awb"]),
    _tool("reschedule", "Book another delivery attempt. slot is today, tomorrow or an ISO date.",
          {"awb": _AWB, "slot": {"type": "string"}}, ["awb", "slot"]),
    _tool("open_rider_dispute", "Open a dispute against the rider's attempt.",
          {"awb": _AWB, "reason": {"type": "string"}}, ["awb", "reason"]),
    _tool("create_refund", "Issue a refund or goodwill credit. kind is refund or goodwill.",
          {"awb": _AWB, "amount_inr": {"type": "integer"}, "kind": {"type": "string", "enum": ["refund", "goodwill"]},
           "vpa": {"type": "string", "description": "UPI id, needed for COD payouts"}},
          ["awb", "amount_inr", "kind"]),
    _tool("escalate", "Hand the case to a human. kind is agent_review or hub_override.",
          {"awb": _AWB, "reason": {"type": "string"},
           "kind": {"type": "string", "enum": ["agent_review", "hub_override"]}},
          ["awb", "reason", "kind"]),
    _tool("close", "Close the conversation with a short resolution note.",
          {"awb": _AWB, "resolution": {"type": "string"}}, ["awb", "resolution"]),
]

_REQUIRED = {t["name"]: t["parameters"]["required"] for t in TOOL_SPECS}


def _flatten_scans(raw):
    return [
        {"ts": s.get("ts"), "status_text": s.get("status_text"), "attempt_n": s.get("attempt_n")}
        for s in raw
    ]


class ToolBox:
    """Executes tool calls. `on_event(kind, data)` receives tool_call / tool_result / tool_timeout."""

    def __init__(self, carrier, policies=None, on_event=None, timeout_s=TOOL_TIMEOUT_S, retries=TOOL_RETRIES):
        self.carrier = carrier
        self.policies = policies or Policies()
        self.on_event = on_event
        self.timeout_s = timeout_s
        self.retries = retries
        self.specs = TOOL_SPECS

    def _emit(self, kind, data):
        if self.on_event:
            self.on_event(kind, data)

    def _invoke(self, name, args, fn):
        last = None
        for attempt in range(self.retries + 1):
            self._emit("tool_call", {"name": name, "args": args, "attempt": attempt})
            try:
                result = fn(timeout_s=self.timeout_s)
            except CarrierTimeout as exc:
                last = exc
                self._emit("tool_timeout", {"name": name, "args": args, "attempt": attempt})
                continue
            self._emit("tool_result", {"name": name, "result": result})
            return result
        return {"error": "carrier_timeout", "detail": str(last) or "no response from carrier"}

    def call(self, name, args):
        """Run one tool call and always return a JSON-able dict."""
        if name not in _REQUIRED:
            return {"error": "unknown_tool", "name": name}
        missing = [k for k in _REQUIRED[name] if k not in args]
        if missing:
            return {"error": "bad_arguments", "missing": missing}
        c = self.carrier
        try:
            if name == "get_shipment":
                return self._invoke(name, args, lambda timeout_s: c.get_shipment(args["awb"], timeout_s=timeout_s))
            if name == "get_scans":
                res = self._invoke(name, args, lambda timeout_s: c.get_scans(args["awb"], timeout_s=timeout_s))
                return res if isinstance(res, dict) else _flatten_scans(res)
            if name == "reschedule":
                return self._invoke(name, args,
                                    lambda timeout_s: c.reschedule(args["awb"], args["slot"], timeout_s=timeout_s))
            if name == "open_rider_dispute":
                return self._invoke(name, args,
                                    lambda timeout_s: c.open_rider_dispute(args["awb"], args["reason"], timeout_s=timeout_s))
            if name == "create_refund":
                amount = int(args["amount_inr"])
                if self.policies.requires_approval(amount):
                    return {"error": "needs_human_approval", "limit_inr": self.policies.approval_limit_inr()}
                return self._invoke(name, args, lambda timeout_s: c.create_refund(
                    args["awb"], amount, args["kind"], vpa=args.get("vpa"), timeout_s=timeout_s))
            if name == "escalate":
                return self._invoke(name, args,
                                    lambda timeout_s: c.escalate(args["awb"], args["reason"], args["kind"], timeout_s=timeout_s))
            return self._invoke(name, args,
                                lambda timeout_s: c.close(args["awb"], args["resolution"]))
        except (KeyError, ValueError, TypeError) as exc:
            return {"error": "tool_failed", "detail": "%s: %s" % (type(exc).__name__, exc)}
