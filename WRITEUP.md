# Fake-attempt NDR handling

## What I found

The dev data is mixed. In `data/dev/dv-002.json`, the parcel has an NDR scan with `attempted: false` and `dur_s: 0`, which supports investigating the complaint. `dv-036` has no call telemetry, and `dv-039` has two NDRs with no telemetry and different reasons. Other NDR examples contain attempted calls. A customer complaint or NDR label alone does not establish what happened at the door.

The traces show the current behavior is to escalate these cases. In `data/traces/trc-011.jsonl`, the bot escalates despite a false, zero-duration call log, then opens a dispute and books a same-day attempt. `trc-101` escalates with a call attempt recorded; `trc-033` and `trc-146` escalate without fetching scans. These traces are observations, not labels of whether the rider actually attempted delivery.

In the code, `SupportAgent` supplies an NDR intent hint that directed complaints to a human. `ToolBox._flatten_scans()` removed the structured scan status and call-log fields, so the model could not see `attempted` or `dur_s`. The default `Policies` class does not decide whether an attempt is fake; the model chooses among the tools offered to it.

## What I changed

I changed `tezdak/tools.py` to retain scan status and expose call telemetry as `attempted` and `dur_s`. Missing telemetry is represented as `None`. I updated the `ndr_complaint` guidance in `tezdak/agent.py`: check shipment and scans; when the last scan is NDR, open a rider dispute and grant Rs 50 goodwill, then reschedule to the earliest available slot if attempts remain. The guidance says not to escalate ordinary fake-attempt cases and not to exceed the three-attempt cap. At the cap it tells the assistant to skip rescheduling and explain that no automatic attempt remains.

I added focused coverage in `tests/test_agent_support.py` for scan-field preservation and a scripted agent-tool sequence that performs the dispute, reschedule, and goodwill calls without escalation. The scripted model verifies that the guidance and tool loop support this sequence; it does not prove a live model will follow it.

## Decisions and limits

Ritika's assignment request asks the bot to treat a last NDR scan as a fake attempt and avoid escalation. The existing product spec instead says NDR complaints go to a human, while the policy docs require a human hub override after three attempts. I followed the requested NDR automation for eligible cases while retaining the three-attempt cap; at the cap, I do not bypass the cap or request an override. The data suggests NDR types and telemetry should be represented accurately in the dispute note, but it does not prove fault.

The refund and goodwill documents conflict: the product spec, September memo, and FAQ list different refund windows and approval limits. The memo caps goodwill at Rs 100 per customer per rolling 30 days; the FAQ says it is given once per customer and for a delivery error on Tezdak's side. I did not reconcile those policy sources or change the underlying policy engine, carrier simulator, or refund rules. The code change uses the requested Rs 50 goodwill action, but its eligibility and repeat-credit behavior still need an authoritative policy decision.

I did not run the unit tests. The scripted test is not a live-model evaluation, and the offline mock planner has canned behavior that still follows the older escalation path. I could not verify live model adherence, the deployed environment's prompt/NLU settings, carrier-side rescheduling availability, or production goodwill enforcement. The product spec's same-day cutoff is 11:00 IST, so "earliest" depends on when the carrier accepts the booking.
