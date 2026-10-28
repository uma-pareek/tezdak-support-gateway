# Service level objectives

Draft agreed in the 2026-10-28 CX sync. Review after the first full month of data.

| Objective | Target | Measured from |
|---|---|---|
| First reply to a customer message | p90 under 12 seconds | gateway timestamps |
| Model calls per turn | at most 6 (hard limit in config) | `llm_usage` events |
| Carrier call timeout | 8 seconds | `tool_timeout` events |
| Hand-over to a human | summary attached to 100 percent of hand-overs | hand-off feature |
| Ticket SLA | 48 business hours, urgent 12, high 24, low 96 | backend `sla.py` |
| Availability of the gateway | 99.5 percent monthly | uptime probe |

Notes
- Ticket hours are multiplied by 0.25 for urgent, 0.5 for high, 1.0 for normal and 2.0 for low.
- Business hours are 09:00 to 21:00.
- Error budget for the gateway is about 3.6 hours a month.
