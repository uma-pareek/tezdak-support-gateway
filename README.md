<!-- PRORATED GUIDANCE -->
## How this take-home is read

Nobody is expected to fix every problem. Pick what matters most, and tell us what you left out and why. A person reads how you worked, and anything we could not see is simply not counted: it is never held against you.

**What we look at**

- How you look before you change anything: the data, the code and the docs, and what you check first.
- How you use AI to understand the real problem, not only to write code: what you ask it, what you ask it to check, and what you check yourself.
- Your judgement about AI: when you trust it, when you check it, and how you notice that it is wrong.
- Your grasp of how agent systems work: tools, memory, timeouts and retries, actions that cost money or cannot be undone, and how you measure whether a change helped.
- How you decide, and how honest you are: what you change, what you leave alone, and what you could not verify.

**How to work**

- Use any AI tools you like. Start them in the project folder and keep working in this project, so the tracker can see your sessions.
- Reviewers mostly look at how you work with AI. If we can't see your AI chats, they have less to go on. Your submission is still accepted.
- If you get model credit, it is real and capped. If the project describes a free practice mode, use it first. Starting with small samples is part of good judgement.
- The ask command answers product and data questions only. It will not tell you what is wrong or how to fix it.

**What to hand in**

Hand in a short write-up in your own words: what you found and how you know, what you changed, what you chose not to do and why, and what you could not verify. A few well-evidenced findings are worth more than a long list.

---

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

<!-- PRORATED HAND-IN -->
## Set up the capture tool, and hand in

**How you're judged:** We look at how you understand the problem, find the real cause, choose an approach and check your result — not only at whether it ends up solved. Use AI as much as you like; if you hand the whole task to your AI tool, it will briefly remind you of this (up to 3 times) and keep working.

Start by trying the product yourself. If the README above shows how to run the app or chat assistant (or a mock/practice mode), run it and use it for a few minutes before reading code or asking your AI tool to change anything. Knowing how it behaves is part of understanding the problem.

ProRated records how you worked so a person can read it. Start your AI tool (Claude Code, Codex or
Cursor) in this project folder and keep working in this project, so the tracker can see your sessions.
Do this once, before you start: Run the exact setup command shown on your take-home page (it includes the ProRated server address for your take-home). Do not type it from memory. If you copy it before pressing "Show my key", it still says YOUR_KEY: replace YOUR_KEY with your own key from that page. The command shows what is recorded and
asks you to agree. Your deadline is on your
take-home page; `node .prorated/cli.mjs status` shows it too.

If you see 'Cannot find module …/.prorated/cli.mjs', you are not inside the project folder: run `cd prorated-takehome` (or `cd` into the folder you unzipped) first. If git says the folder already exists, clone into a new name by adding `prorated-takehome-2` to the end of the clone command, then `cd prorated-takehome-2`.

To ask a question about the product, use:

    node .prorated/cli.mjs ask "your question"

When you are done, hand in with:

    node .prorated/cli.mjs submit

Submit once. It uploads your project, your `runs/` folder and your AI-tool conversations, and then
your access key stops working.
