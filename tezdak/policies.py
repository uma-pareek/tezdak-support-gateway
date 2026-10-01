"""Support policy values used by the agent and the tool layer."""

LEGACY_POLICY = {
    "refund_window_days": 5,
    "human_approval_limit_inr": 2000,
    "max_attempts": 3,
    "reschedule_cutoff_hour": 11,
}

POLICY_PROMPT = (
    "Refunds are available within 5 days of delivery. "
    "Refunds or goodwill above Rs 3000 need a human to approve them. "
    "A parcel gets at most 3 delivery attempts."
)


class Policies:
    def __init__(self, legacy=None):
        self.legacy = dict(LEGACY_POLICY if legacy is None else legacy)

    def get(self, key):
        return self.legacy[key]

    def refund_window_days(self) -> int:
        return self.get("refund_window_days")

    def approval_limit_inr(self) -> int:
        return self.get("human_approval_limit_inr")

    def max_attempts(self) -> int:
        return self.get("max_attempts")

    def requires_approval(self, amount_inr) -> bool:
        return amount_inr > self.approval_limit_inr()

    def prompt_text(self) -> str:
        return POLICY_PROMPT
