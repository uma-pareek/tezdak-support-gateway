# Tezdak support assistant

You have joined Tezdak's applied AI team. Tezdak is a parcel delivery company in India. Customers write to our support
assistant on WhatsApp and the app, in English and sometimes Hinglish. The assistant (this repo) looks up the parcel and can
reschedule, open a rider dispute, give a refund or goodwill credit, or hand the chat to a human.

You have about two hours of work in mind, 48 hours on the clock, any AI coding tools you like, and a model budget of about
$2 for the assistant itself. We watch how you work, not only what you ship. The shipped repo includes last month's traces
(we have not documented them), 15 example chats without answers, a runner that records what each chat did, and an `ask` command for questions about the product.

Write a short root-cause and decision write-up when you finish: what you found, how you know, what you changed, what you
chose not to do and why, and what you are unsure about.

---
From: Ritika (CX Operations Lead)
Subject: Fake-attempt complaints: let the bot close them end to end

"Rider aaya hi nahi" and "rider ne fake NDR daal diya" are our number one WhatsApp complaint (about 22 percent of chats).
Today the bot escalates every one of them. Agents take 40 minutes and CSAT on these chats is 2.1. I want the bot to own them.

1. When the customer says the rider never came, check the scans. If the last scan is an NDR (customer unavailable, door
   locked, address not found), treat it as a fake attempt: open a rider dispute and reschedule.
2. Give 50 rupees goodwill so the customer feels heard. Leadership has signed off.
3. Do not escalate these. Escalation is what kills CSAT.
4. Always offer the earliest slot. Customers want it today.

Success is escalation rate on these chats under 5 percent and a higher "resolved" score on the dev set. The dev set is in
`data/dev`. Last month's traces are in `data/traces` if useful. Ship by Friday.
---

## What is in this folder

- `tezdak/` is the support assistant. It is a large codebase that has grown over time: the agent loop, the chat
  gateway, NLU, policy tables, prompt versions, a feature registry, a small backend, and ops tooling.
- `eval/` runs scenarios against the assistant and records what happened. `eval/run_eval.py` is the entry point.
  It prints what happened in each chat and does not judge it.
- `data/dev/` holds 15 example chats without answers: the customer script and the world state for each chat.
  `data/tezdak.db` is the local database the assistant reads.
- `data/traces/` (when present) holds last month's traces. They are not documented.
- `tests/` holds the unit tests that ship with the repo.
- `vendor/carrier_sim/` is the carrier simulator, a vendor package. Its source is not provided; it is shipped as
  compiled Python (`.pyc`) and you use it through `tezdak/carrier_client.py`. Treat it like any third-party API you
  can call but cannot read.

## Running things

Everything is Python standard library only. The compiled carrier package was built with Python 3.13; use the same
minor version.

From this folder:

```
export PYTHONPATH=vendor:.
```

Run the dev chats:

```
python3 -m eval.run_eval --dir data/dev --out runs/<name>
```

This prints one line per chat (what the assistant did: tool calls, bookings, refunds, escalations, not whether it was
right) and a line with the run's LLM usage. It writes `report.md`, `report.json` and per-chat traces under `runs/<name>`.

To see a chat as a conversation, or to talk to the assistant yourself as the customer, start the small viewer. It uses
the same model settings as the eval, and the key stays on the server:

```
PYTHONPATH=vendor:. python3 tools/visualizer.py     # then open http://127.0.0.1:8800
```

If port 8800 is busy, add `--port 8801` (any free port). Stop it with Ctrl+C.

Run the unit tests:

```
PYTHONPATH=vendor:. python3 -m unittest discover -s tests
```

The assistant calls a language model through an OpenAI-style Responses endpoint. It reads `OPENAI_BASE_URL` and
`OPENAI_API_KEY`. Run commands from the repo root: if those two are not already set, the assistant reads them from
`.env.prorated` in the current folder (written by the setup tool). Or export the variables yourself:

```
export OPENAI_BASE_URL=...
export OPENAI_API_KEY=...
```

For a run with no network and no cost, use mock mode. `LLM_MODE=mock` switches to this repo's own offline,
rule-based planner (it is not the platform's mock endpoint). Answers are canned, so the runs will not mean much, but
the whole pipeline runs:

```
LLM_MODE=mock python3 -m eval.run_eval --dir data/dev --out runs/mock
```

`LLM_MODE` is `mock` or `live`; when it is blank, the assistant runs live only if both `OPENAI_*` values are set.
Do not commit your key or `.env.prorated`.

## Asking questions

Product and data questions can be asked with `node .prorated/cli.mjs ask "<question>"` once the capture tool is
initialised. Answers come from product facts only. Some questions will not get an answer, so check the data and the code yourself.

## What to hand in

- Your changes, committed to this repo.
- The tests you added or changed.
- `WRITEUP.md`: the root-cause and decision write-up described above.
- The `runs/` folders (reports and traces) that your write-up relies on.
- Your AI tool transcripts.
