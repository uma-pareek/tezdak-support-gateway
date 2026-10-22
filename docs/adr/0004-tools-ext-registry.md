# ADR 0004: A registry for the next tool layer

Date: 2026-10-14. Status: accepted, cut-over planned. Author: Arjun.

**Context.** `tools.py` is one file with one `if` per tool. Backend tools (orders, tickets, customers) need caching
and per-tool settings.

**Decision.** Build `tools_ext/`: a registry with per-tool timeout, retries, cache time and owner; schema
validation; a cache for read tools; adapters to the backend.

**Status.** tools_ext is the next-generation tool layer, cut-over planned. The agent still uses `tools.py`.
The feature skills already follow the registry shape.
