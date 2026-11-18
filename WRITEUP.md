# Tezdak Support Assistant - Take-Home Writeup

## What I Found

When digging into the dev data (`data/dev/`), the scenarios for missed deliveries or fake NDRs are mixed. In `dv-002`, the parcel has an NDR scan with `attempted: false` and `dur_s: 0`, which gives us concrete telemetry to investigate. However, other scenarios like `dv-036` and `dv-039` lack call telemetry or have multiple NDR reasons. This showed us that an NDR status or a customer complaint by itself doesn’t automatically prove rider misconduct.

Looking at historical traces, the assistant previously routed these complaints straight to human escalation (e.g., `trc-011`, `trc-101`, `trc-033`), often without even inspecting the underlying scan evidence. 

In the codebase, `SupportAgent` used an NDR hint that pushed complaints toward a human agent. Furthermore, `ToolBox._flatten_scans()` was stripping out structured scan status and call-log fields, meaning the LLM never had access to key fields like `attempted` or `dur_s`.

## What I Changed

1. **Exposed Telemetry (`tezdak/tools.py`):** Updated `get_scans` so that scan statuses and call-attempt telemetry (`attempted` and `dur_s`) are properly preserved and returned to the model (defaulting to `None` if missing).
2. **Updated NDR Policy Guidance (`tezdak/agent.py`):** Revised the `ndr_complaint` instructions. The agent now checks shipment and scan history: when a fake attempt is detected, it opens a rider dispute, grants a ₹50 goodwill credit, and reschedules to the earliest available slot. It avoids unnecessary human escalation unless max attempt limits (3 attempts) are hit.
3. **Added Focused Tests (`tests/test_agent_support.py`):** Created dedicated test coverage confirming that scan telemetry is retained and that the agent executes the dispute, rescheduling, and goodwill tool sequence without prematurely escalating.

## Decisions and Limits

- **Balancing Policy vs. Ritika's Request:** Ritika's brief requested treating last NDR scans as fake attempts and bypassing escalation. While official docs historically pointed NDRs to human handoff and hub overrides after three attempts, I implemented the requested automation for eligible cases while strictly respecting the three-attempt limit (skipping rescheduling when exhausted).
- **Goodwill & Policy Conflicts:** Existing documentation contained conflicting rules regarding refund windows, approval thresholds, and goodwill caps (e.g., monthly rolling caps vs. once-per-customer limits). I implemented the requested ₹50 goodwill action via the available tools, but noted that broader deduplication and policy rule harmonization remain open items.
- **Verification:** Unit tests and local eval runs were executed to ensure code stability and correct tool-calling sequences, though live-model behavior will naturally depend on real-time prompt generation and carrier slot availability.