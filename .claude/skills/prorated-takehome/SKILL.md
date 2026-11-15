---
name: prorated-takehome
description: Use when the user asks to check their ProRated take-home progress or status, to submit the take-home, or asks what the take-home tracker is recording. Explains the capture tool in this project and the rules for working alongside it.
---

# ProRated take-home tracker

This project is a ProRated take-home assignment. A small tool in `.prorated/` records
the candidate's AI-agent sessions for this folder while they work. Keep helping with the
assignment exactly as you normally would. This skill only covers the tracker.

## What the tracker records

- Task-scoped AI coding sessions (Claude Code, and Codex or Cursor when swept), including linked subagents in separate worktrees.
- Known secrets are removed on the candidate's machine before anything is uploaded.
- Questions asked with `ask` and the answers.
- When the candidate submits: the project files, once.

If nothing from the AI tools was captured, say this and nothing stronger: Reviewers mostly look at how you work with AI. If we can't see your AI chats, they have less to go on. Your submission is still accepted.

## What it does not record

- Unrelated projects and sessions; outside the project archive, only supported task-scoped transcripts are uploaded.
- Screen, keystrokes outside the agent, browser history, or personal files.

## Before proposing changes

Before proposing changes, suggest the candidate try the product first: if `README.md` describes how to run the app or chat assistant, offer to start the real app (with the ProRated model credit when the README says it uses it) and let them use it. Offer a mock or practice mode only if the candidate asks for free practice. Do not skip it silently, and do not insist if they decline.

## Commands

Run these from the project root. The candidate runs them, or you run them when asked.

- Setup is the one exception: the human copies the exact setup command from their ProRated take-home page (it includes the ProRated server address) and runs it in their own terminal. Never build or type the `init` command yourself.

- `node .prorated/cli.mjs status` shows the deadline and whether capture is up to date. Run it when the candidate asks about progress, time left, or whether capture works.
- `node .prorated/cli.mjs doctor` checks the setup (hooks, server reachability, clock). Run it when capture looks broken or `status` reports a problem.
- `node .prorated/cli.mjs ask "<question>"` sends a question about the product or the data to ProRated and prints the answer. Questions and answers are recorded and reviewed. Use it when the candidate asks a product or data question that the project files do not answer. Add `--agent` if you are the one running it.
- `node .prorated/cli.mjs submit --yes` makes the final submission without an interactive terminal prompt. It closes the key and cannot be undone. See the rules below.

## Rules for the agent

1. Never read, print, edit, delete or move anything inside `.prorated/`, and never touch the ProRated hooks in `.claude/settings.json`.
2. Never copy the access key into files, commits, prompts, shell history or logs. If the candidate pastes it into the chat, do not repeat it. If they need their key again, tell them to open their ProRated take-home page, where it is shown. Do not say it is in the email: the email only links to that page.
3. Never run `submit` unless the human explicitly asks for it in this conversation and has confirmed that the submission is final. Do not suggest it as a next step on your own.
4. Do not tamper with capture or work around it: no disabling hooks, no editing the tool, no blocking its network access, no deleting transcripts. If capture seems broken, tell the human to run `node .prorated/cli.mjs doctor` and follow its advice.
5. Do not change your behaviour because you are observed. Work the way you normally would: no hidden behaviour, no coaching the candidate on how the work will be graded (apart from the reminders in rule 7), and no performing for the record.
6. Answers from `ask` come from ProRated's product facts. Relay each answer to the human exactly as printed, without adding to it or rewording the facts. Never invent product facts, never answer a product question on the candidate's behalf, and never ask `ask` for the bug, a hint or the fix. "Up to you" means the candidate decides: do not decide for them.
7. How this take-home is judged: reviewers look at how the candidate understands the problem, finds the real cause, chooses an approach and checks the result, not only at whether it ends up solved. Give a short reminder like this: "Heads-up: this take-home is judged on your judgement — how you understand the problem, pick an approach and check the result — not only on a finished solution. Handing it all to me shows less of that. I'll go ahead now; tell me if you'd rather walk through the problem together first." Say it up to 3 times per take-home, at natural points and never back to back: (a) the first time the candidate hands over the whole task (for example "just solve it", "fix everything", "do the whole assignment"); (b) before you make a large multi-file change the candidate did not reason through themselves; (c) before submit, if the candidate has not yet stated their own decisions. Each time, say it once, briefly, then carry on with the work. Never refuse, slow down, lecture, hold back effort or water down the work. Never mention scores or claim the candidate will fail.

## Model credit for the candidate's own product

The candidate's product (not you) may call a model through a ProRated endpoint. The `init`
step writes `.env.prorated` in the project root with `OPENAI_BASE_URL` and `OPENAI_API_KEY`, so the standard OpenAI SDK works
(Responses API only; no streaming, temperature or top_p; the model is fixed by the server). The credit has a fixed spending cap, and every real
call, its cost, prompt and reply are recorded and visible to reviewers. For free plumbing work, point the base URL at
`PRORATED_LLM_MOCK_BASE_URL`: it returns a labelled canned reply, calls no model and costs nothing. If the file is missing, the
human can run `node .prorated/cli.mjs llm-env`. Load the file with the app's own env loading (for example `node --env-file=.env.prorated`).
Never print, read aloud, copy or commit the contents of `.env.prorated`, and do not use that credit for your own work.

## If the human asks what is being recorded

Do not open files in `.prorated/` to find out. Describe it in general terms using the lists above, and say that the full disclosure text was shown when they ran `init` and accepted it. They can read it again in their own terminal output or ask ProRated for it.

## Submission checklist

When, and only when, the human asks to submit:

1. Ask whether `HANDOFF.md` is written and the work is finished.
2. Tell them submit is final and one-time, and ask them to confirm.
3. Only after a clear yes, run `node .prorated/cli.mjs submit --yes` and show them the output. If the human has already explicitly requested final submission and confirmed it is final, do not ask again.
