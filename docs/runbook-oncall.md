# On-call runbook

Written by Kabir, updated by Meera on 2026-11-06. Rota is in the team calendar.

## First five minutes
1. Is the gateway taking messages? Send "hi" from the test number. You should get a reply within 15 seconds.
2. Check the mode: `LLM_MODE` must be `live` in production. In `mock` mode replies are canned.
3. Check the carrier: see [runbook-carrier.md](runbook-carrier.md). A slow carrier looks like slow chats.
4. Look at the last hour on the dashboard: [dashboard-definitions.md](dashboard-definitions.md).

## Common situations
| Symptom | Look at | Usual action |
|---|---|---|
| No replies at all | Gateway process, webhook URL | Restart the process; session state is in memory, so open chats lose their window of 12 messages. |
| Replies say "A colleague will follow up" | Model calls per turn (limit 6) | Check the LLM endpoint and token. |
| Many `tool_timeout` events | Carrier latency | Wait it out; escalate to the carrier contact if it lasts over 30 minutes. |
