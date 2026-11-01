# ADR 0006: One JSONL file per scenario for traces

Date: 2026-10-30. Status: accepted. Author: Kabir.

**Context.** We want to read what the agent did without a database.

**Decision.** One JSON object per line with `scenario`, `seq`, `t`, `kind`, `data`. Kinds are listed in
[eval-howto.md](../eval-howto.md). Keys are sorted so diffs between runs are readable.

**Consequences.** Easy to grep and to load in a notebook. Every event is validated on write and on read.
