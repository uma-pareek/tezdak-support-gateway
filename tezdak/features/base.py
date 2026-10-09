"""Feature plug-in base types.

Changelog
  0.2  FeatureContext carries the backend handle next to the carrier.
  0.1  First cut: Feature with can_handle / tool_specs / run_tool / prompt_hint.
"""

from dataclasses import dataclass


@dataclass
class FeatureContext:
    awb: str | None
    user_text: str
    intent: str
    language: str          # "english" | "hinglish"
    carrier: object        # CarrierClient-like
    backend: object        # tezdak.backend.facade.Backend-like (duck-typed; see D)
    policies: object       # tezdak.policies.Policies-like
    now: object            # aware datetime or None


class Feature:
    name: str = ""
    intents: tuple = ()

    def can_handle(self, ctx: FeatureContext) -> bool:
        return ctx.intent in self.intents

    def tool_specs(self) -> list:
        return []

    def run_tool(self, name: str, args: dict, ctx: FeatureContext) -> dict:
        return {"error": "unknown_tool", "name": name}

    def prompt_hint(self, ctx: FeatureContext) -> str:
        return ""
