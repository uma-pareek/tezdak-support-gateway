# Eval how-to

## Run it
From the repo folder, with `PYTHONPATH` set so `tezdak` and `carrier_sim` import:

    python3 -m eval.run_eval --dir data/dev --out runs/my-run

`--dir` is a folder of scenario JSON files. `--out` is the run folder. The command prints one line per chat, an
LLM usage line and the path of the report. With no LLM variables set the client is in `mock` mode and costs nothing.

## What a run folder holds
- `report.md` and `report.json`.
- One JSONL trace per scenario under `traces/`.

## Reading the report
The report lists what happened. It does not say whether a chat went well; that is for you to decide.

- Per chat: customer turns, tool calls (name, arguments, attempt), the carrier ledger (type, AWB, arguments,
  result), delivery attempts used, bookings made, refunds paid with amounts, whether the chat was escalated and
  whether it was closed, and LLM calls, tokens and spend.
- LLM line: calls, tokens and spend for the whole run. Rates in dollars per million tokens: 0.10 uncached input, 0.01 cached input, 0.50 output.
- Change since previous run: which files under `tezdak/` changed since the last run folder next to this one.

## Traces
Traces are written as JSONL, one event per line, with exactly these fields: `scenario`, `seq`, `t`, `kind`, `data`.
Saved traces from earlier runs live in `data/traces`, one file per scenario.

Event kinds:
| Kind | Meaning |
|---|---|
| `session_start` | A chat begins. |
| `customer_msg` | A customer line. |
| `agent_msg` | The assistant's reply. |
| `tool_call` | A tool call; data has `name`, `args`, `attempt`. |
| `tool_result` | What the tool returned. |
| `tool_timeout` | A tool call that did not finish within its timeout. |
| `ledger` | An action recorded by the carrier. |
| `llm_usage` | Token counts for a model call. |
| `feature_call`, `feature_result` | A feature skill was called and what it returned. |

To read a trace quickly: filter on `kind`, then follow `seq` in order.
