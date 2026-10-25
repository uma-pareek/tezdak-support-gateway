# ADR 0005: Keep policy generations side by side

Date: 2026-10-16. Status: accepted. Author: Sunil.

**Context.** Ops changes policy numbers a few times a year and wants to compare the old and new answer for the same claim.

**Decision.** `tezdak/policy/` has v1 (2025 handbook), v2 (ops table) and v3 (September memo), each with the same
methods, and `compare.py` to run one claim through several. `TEZDAK_POLICY_GEN` picks one; default is v2.

**Status.** policy v3 not yet wired into the agent. The agent keeps reading `policies.py` until the cut-over.
