"""NLU package: rules-based v1 classifier, LLM-assisted v2, shared normalizer and entities.

Changelog
- 0.1  rules_v1 and normalizer carved out of the old router.
- 0.2  entities and language detection.
- 0.3  intents_v2, shadow comparison, engine flag.
Use `tezdak.nlu.facade.classify` as the single entry point.
"""

__all__ = ["facade", "flags", "normalizer", "entities", "language", "rules_v1", "intents_v2", "shadow"]
