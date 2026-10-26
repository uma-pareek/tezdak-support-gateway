# Architecture

Last touched: 2026-10-26 (Meera). This is a map of the repo as it stands, not a design wish list.

## One-paragraph version

A customer message arrives on WhatsApp or the in-app chat. The **gateway** cleans it up and hands it to the
**support agent**. The agent classifies the message with a keyword router, builds a system prompt, and runs a short
tool loop against the model (at most 6 model calls per turn). Tools talk to the **carrier** through a thin client.
Everything the agent does is recorded as events, and the eval harness turns those events into traces.

## Packages

| Package | What it does | State |
|---|---|---|
| `tezdak/gateway/` | WhatsApp and app-chat intake, session window, message de-noising, rate limit, reply splitting, voice-note handling. | In use on the message path. Status callbacks, webhook verification and `send_proactive` are built but not on the message path. |
| `tezdak/agent.py` | `SupportAgent.handle()`: classify, prompt, tool loop, ETA line to commitments. | In use. See [CHANGELOG](CHANGELOG.md) 0.1 to 0.4. |
| `tezdak/router.py` | Keyword intent router (English and Hinglish). Five intents. | In use. |
| `tezdak/tools.py` | Seven function tools the model can call, with a per-call timeout of 8 s and a small attempt wrapper. | In use. |
| `tezdak/carrier_client.py` | Thin client over the carrier API. The simulator stands in for the carrier in this repo. | In use. |
| `tezdak/policies.py` | Policy numbers and the prompt text the agent reads today. | In use. |
| `tezdak/policy/` | Policy generations v1, v2, v3 plus goodwill and eligibility helpers. | policy v3 not yet wired. The agent still reads `policies.py`. |
| `tezdak/tools_ext/` | Next-generation tool layer: registry, schemas, cache, executor, backend adapters. | tools_ext is the next-generation tool layer, cut-over planned. The agent uses `tools.py` today. |
| `tezdak/nlu/` | Rule engine v1, intents v2, shadow comparison, entity and language helpers. | Behind `TEZDAK_NLU_ENGINE` (unset by default, so the keyword router runs). |
| `tezdak/features/` | Optional skills (address update, cancel, COD refund, rider feedback, hand-off summary, and more). | Planner is built when a backend is passed. Three skills are switched off by default (`FEATURES_OFF_BY_DEFAULT` in `agent.py`). Some skills only appear when the newer NLU emits their intent. |
| `tezdak/prompts/` | Prompt versions v1 to v6, hint files, Hinglish style files. | Behind `TEZDAK_PROMPT_VERSION` (unset by default, so the prompt in `agent.py` is used). |
| `tezdak/backend/` | SQLite-backed stores for orders, tickets, customers, settings, events, plus a seed and a facade. | In use through `Backend`. |
| `eval/` | Scenario runner, scripted customers, traces, a report of what each chat did. | See [eval-howto](docs/eval-howto.md). |

## Request flow

1. `gateway.router.Gateway.on_message(raw, channel)` parses the webhook, drops repeats, applies the rate limit and
   keeps the last 12 messages of the session (6 hour window).
2. `SupportAgent.handle(conversation)` finds the AWB (a `TZ` plus six or more digits) in the chat.
3. The message is classified: `router.classify` (or `nlu.facade.classify` when `TEZDAK_NLU_ENGINE` is set).
4. The system prompt is rendered with the AWB, today's date, intent, language, the attempt limit (3) and a
   one-line hint for the intent.
5. The tool loop runs. Each tool call goes through `ToolBox.call` to `CarrierClient`. The model sees results as JSON.
6. The reply ends with an `ETA:` line. `eta_commitments` strips it and returns a structured commitment.
7. `Metrics.record` counts the chat. The gateway formats and splits the reply for the channel.

## Tools the model can call

`get_shipment`, `get_scans`, `reschedule`, `open_rider_dispute`, `create_refund`, `escalate`, `close`.
Refunds above the approval limit in `policies.py` return `needs_human_approval` and the model is expected to hand over.

## Configuration

Environment variables only. `OPENAI_BASE_URL`, `OPENAI_API_KEY` (read from `.env.prorated` in the working
directory when not set), `LLM_MODE` (`mock` or `live`), `LLM_REPLAY_REASONING` (default `1`),
`TEZDAK_NLU_ENGINE`, `TEZDAK_PROMPT_VERSION`, `TEZDAK_POLICY_GEN`, `TEZDAK_FEATURES_DISABLED`, and the
`TEZDAK_GW_*` family for the gateway. Without an LLM base URL and key the client runs in `mock` mode.
The client posts to `<OPENAI_BASE_URL>/responses` and retries 429, 502 and 503 up to three times.

## Half-migrated pieces, in one place

- tools_ext is the next-generation tool layer, cut-over planned (owner: Arjun; see [ADR 0004](docs/adr/0004-tools-ext-registry.md)).
- policy v3 not yet wired; `policies.py` is still what the agent reads ([ADR 0005](docs/adr/0005-policy-generations.md)).
- NLU v2 and shadow mode are waiting for the labelled set Kabir is putting together.
- Prompt versions v5 and v6 exist for trials; v4 is the default of the loader, the inline prompt is the default of the agent.

## Tests

`python3 -m unittest discover -s tests` from this folder, with the vendor folder holding `carrier_sim` on `PYTHONPATH`.
Tests that need the simulator skip themselves when it is missing.
