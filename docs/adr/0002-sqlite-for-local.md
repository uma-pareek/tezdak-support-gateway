# ADR 0002: SQLite for the local backend

Date: 2026-10-06. Status: accepted. Author: Meera.

**Context.** Orders, tickets, customers and settings need a store for development and tests.

**Decision.** Use SQLite from the standard library. `Backend.in_memory()` for tests, a file for local runs.
Production will use the main database through the same facade.

**Consequences.** No extra dependency, fast tests. Schema changes go through small migrations in `backend/db.py`.
