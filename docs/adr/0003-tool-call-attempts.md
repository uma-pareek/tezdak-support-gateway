# ADR 0003: Attempt wrapper on tool calls

Date: 2026-10-20. Status: accepted. Author: Arjun.

**Context.** The carrier is flaky on Mondays. Calls that time out ended chats with an apology, and customers left.

**Decision.** `ToolBox` makes up to 2 further attempts when a call times out, with the same 8 second timeout each,
and emits `tool_call` and `tool_timeout` events for every attempt so traces show what happened.
After the last attempt the model receives `{"error": "carrier_timeout"}`.

**Consequences.** Retries added to keep chats alive; fewer apologies on Mondays. The attempt number is recorded
in each `tool_call` event.
