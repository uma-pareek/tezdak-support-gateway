"""Support policy values used by the agent and the tool layer.

v2 values are being rolled out key by key (see V2_KEYS).
"""

LEGACY_POLICY = {
    "refund_window_days": 5,
    "human_approval_limit_inr": 2000,
    "max_attempts": 3,
    "reschedule_cutoff_hour": 11,
}

POLICY_V2 = {
    "refund_window_days": 7,
    "human_approval_limit_inr": 5000,
}

V2_KEYS = {"refund_window_days"}

POLICY_PROMPT = (
    "Refunds are available within 10 days of delivery. "
    "Refunds or goodwill above Rs 3000 need a human to approve them. "
    "A parcel gets at most 3 delivery attempts."
)


class Policies:
    def __init__(self, legacy=None, v2=None, v2_keys=None):
        self.legacy = dict(LEGACY_POLICY if legacy is None else legacy)
        self.v2 = dict(POLICY_V2 if v2 is None else v2)
        self.v2_keys = set(V2_KEYS if v2_keys is None else v2_keys)

    def get(self, key):
        if key in self.v2_keys and key in self.v2:
            return self.v2[key]
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
