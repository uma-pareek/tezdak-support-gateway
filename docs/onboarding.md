# Onboarding

Welcome. This takes about half a day.

1. Read [ARCHITECTURE.md](../ARCHITECTURE.md) and the [product spec](product-spec.md).
2. Read the [glossary](glossary.md); the parcel words come up everywhere.
3. Python 3.11 or newer. The code uses the standard library only.
4. Run the tests: `python3 -m unittest discover -s tests` from the repo folder. If the simulator is not importable,
   some tests skip. Set `PYTHONPATH` to the folder that holds `carrier_sim`.
5. Try the eval on the dev scenarios: see [eval-howto.md](eval-howto.md). Without LLM variables set, the client runs in `mock` mode.
6. Pick a small first change. Good ones: a Hinglish phrase in the style files, a new regex in the router, a test.

## Who to ask
- Agent loop and prompts: Arjun.
- Gateway and on-call: Meera.
- NLU and eval: Kabir.
- Policy numbers and CX questions: Ritika and Sunil.

## Habits
- Small commits. A test with every change.
- Put secrets in environment variables, never in the repo.
