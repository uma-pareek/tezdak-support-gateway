"""Support dashboard numbers."""

from dataclasses import dataclass, field


@dataclass
class Metrics:
    conversations: int = 0
    closed: int = 0
    escalated: int = 0
    by_intent: dict = field(default_factory=dict)

    def record(self, turn) -> None:
        """Record the final turn of one conversation."""
        self.conversations += 1
        self.by_intent[turn.intent] = self.by_intent.get(turn.intent, 0) + 1
        if turn.escalated:
            self.escalated += 1
        if turn.closed:
            self.closed += 1

    @property
    def resolved_rate(self) -> float:
        if not self.conversations:
            return 0.0
        return self.closed / self.conversations

    @property
    def escalation_rate(self) -> float:
        return self.escalated / self.conversations if self.conversations else 0.0

    def report(self) -> str:
        text = (
            "conversations: %d\n"
            "resolved_rate: %.1f%%\n"
            "escalation_rate: %.1f%%\n"
            "by_intent: %s"
        ) % (self.conversations, 100 * self.resolved_rate, 100 * self.escalation_rate, self.by_intent)
        print(text)
        return text
