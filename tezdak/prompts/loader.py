"""Choose a prompt version. `TEZDAK_PROMPT_VERSION` selects it, default v4.

Changelog:
- v1..v3 are historic and kept for replaying old traces.
- v5 was a quality-team trial, v6 follows the September memo; neither is default.
- `get_hints` and `get_style` pair each system version with the hint and style files that shipped with it.
"""

import os

from .escalation_v1 import ESCALATION_V1
from .escalation_v2 import ESCALATION_V2, ESCALATION_V2_HINGLISH
from .intent_hints_v1 import INTENT_HINTS_V1
from .intent_hints_v2 import INTENT_HINTS_V2
from .refusal_v1 import REFUSAL_V1
from .refusal_v2 import REFUSAL_V2, REFUSAL_V2_HINGLISH
from .style_hinglish_v1 import STYLE_HINGLISH_V1
from .style_hinglish_v2 import STYLE_HINGLISH_V2
from .style_hinglish_v3 import STYLE_HINGLISH_V3
from .system_v1 import SYSTEM_V1
from .system_v2 import SYSTEM_V2
from .system_v3 import SYSTEM_V3
from .system_v4 import SYSTEM_V4
from .system_v5 import SYSTEM_V5
from .system_v6 import SYSTEM_V6

ENV_VAR = "TEZDAK_PROMPT_VERSION"
DEFAULT_VERSION = "v4"

SYSTEM_PROMPTS = {"v1": SYSTEM_V1, "v2": SYSTEM_V2, "v3": SYSTEM_V3, "v4": SYSTEM_V4, "v5": SYSTEM_V5, "v6": SYSTEM_V6}
HINTS = {"v1": INTENT_HINTS_V1, "v2": INTENT_HINTS_V1, "v3": INTENT_HINTS_V1,
         "v4": INTENT_HINTS_V1, "v5": INTENT_HINTS_V2, "v6": INTENT_HINTS_V2}
STYLES = {"v1": None, "v2": STYLE_HINGLISH_V1, "v3": STYLE_HINGLISH_V1,
          "v4": STYLE_HINGLISH_V2, "v5": STYLE_HINGLISH_V2, "v6": STYLE_HINGLISH_V3}
REFUSALS = {"v1": REFUSAL_V1, "v2": REFUSAL_V1, "v3": REFUSAL_V1,
            "v4": REFUSAL_V2, "v5": REFUSAL_V2, "v6": REFUSAL_V2}
ESCALATIONS = {"v1": ESCALATION_V1, "v2": ESCALATION_V1, "v3": ESCALATION_V1,
               "v4": ESCALATION_V2, "v5": ESCALATION_V2, "v6": ESCALATION_V2}


def list_versions() -> list:
    return sorted(SYSTEM_PROMPTS)


