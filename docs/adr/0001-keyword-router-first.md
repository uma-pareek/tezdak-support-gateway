# ADR 0001: Keyword router before any model-based classifier

Date: 2026-10-02. Status: accepted. Author: Arjun.

**Context.** We needed an intent before the model runs so that the prompt can carry a short hint. A model call
for classification adds cost and time to every message.

**Decision.** Start with a regex router (`router.py`) with five intents, English and Hinglish spellings.

**Consequences.** Cheap, easy to read, easy to fix by hand. It misses rare phrasings. The NLU package (see CHANGELOG 0.6) is the planned next step, switched on with `TEZDAK_NLU_ENGINE`.
