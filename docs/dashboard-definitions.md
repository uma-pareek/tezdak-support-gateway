# Dashboard definitions

The CX dashboard and `tezdak.metrics.Metrics` use these definitions. Written by Ritika's team, 2026-10-12.

| Metric | Definition |
|---|---|
| conversations | Chats the assistant handled to a final reply. |
| closed | Chats where the assistant called `close`. |
| escalated | Chats where the assistant handed over to a human. |
| resolved (resolved rate) | Chats closed without an escalation, divided by all conversations. |
| escalation rate | Escalated chats divided by all conversations. |
| by intent | Count of conversations per detected intent. |
| latency p50, p90, p99 | Nearest-rank percentiles of reply time in milliseconds. |
| spend | Model tokens priced at the posted rate; see [eval-howto.md](eval-howto.md) for the rate. |

The eval report does not compute dashboard metrics. It lists, per chat, whether the chat was escalated and whether it was closed.
