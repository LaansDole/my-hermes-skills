---
name: oh-my-pi
description: "Troubleshoot/operate the Oh-My-Pi (omp) coding agent."
---

# Oh-My-Pi (omp) Coding Agent

## Identity & disambiguation
- can1357/oh-my-pi — the fork the user actually runs, with Claude Opus 5 as its saved model. It is a heavily customized fork of earendil-works/pi ("Pi agent harness", pi.dev): packages are `@oh-my-pi/*`, with the unified `hub` tool, hash-anchored edits, LSP.
- Do NOT confuse with earendil-works/pi (the upstream). If the user says "pi", confirm which. The user corrected exactly this confusion (Aug 2026) — "I am using Claude Opus 5 on Oh-My-Pi".
- Config root: `~/.omp/`. Bundled agents live in-repo at `packages/coding-agent/src/prompts/agents/*.md`.

## Portable dotfiles (LaansDole/omp-preset)

The reproducible home for this skill's subject is the **omp-preset** repo:
https://github.com/LaansDole/omp-preset. It versions the source-of-truth `config.yml`,
the custom task agents (`reviewer`, `reviewer-deep`, `tldr`, `pr`), `WATCHDOG.md`, the
plugin install manifest, and the `writing-pr-descriptions` skill, plus a sandbox-verified
`bootstrap.sh` that installs them into the active omp profile. Not a fork: it always
installs the latest omp binary and carries only the portable user-scope layer.
`git clone .../omp-preset && ./bootstrap.sh` reproduces this harness on another machine.

## hub tool — the coordination surface
- One tool for: peer messaging (`send`/`inbox`/`list`), background jobs (`wait`/`jobs`/`cancel`), and process supervision (`start`/`ps`/`logs`/`stop`/`restart`/`describe`). Always registered.
- `hub wait` is a RACE: first watched running job's promise | first matching peer message | wait window | steering abort. It returns on the FIRST event — never "when everything finishes"; the model re-issues to keep waiting. Job results self-deliver even if the agent stops waiting.
- `wait` is INTERRUPTIBLE by design (`interruptible = op === "wait"`). A user steering message aborts it, and the returned snapshot then shows "## Still Running" — which the code flags as a `useless` frame, rendered as a displaceable waiting frame. **"Still Running" is normal, NOT a stall.**
- Wait timeouts are normal results, never errors.

## Poll window (why waits LOOK stuck)
- `async.pollWaitDuration` defaults to `smart`: ladder `[5s, 10s, 30s, 60s, 300s]`, climbing per back-to-back wait, resetting after 60 s without waiting. A single wait can block up to 5 min, and every re-issue costs a full LLM round-trip. Fixed settings: `5s`/`10s`/`30s`/`1m`/`5m`.
- `timeoutMs` 0 = wait indefinitely.

## Task agents & model routing
- `task` tool spawns subagents from agent definitions. Bundled agents are overridden by user agents (`~/.omp/agent/agents/*.md`) and project agents (`.omp/agents/*.md`); precedence: extension roots > marketplace plugins > bundled.
- `reviewer` agent: `model: "@slow"`. `@slow` resolution tries the user's SAVED model FIRST (findSlowModel) — on this user's setup that is Claude Opus 5. Read-only tools (read, grep, glob, bash-read-only, lsp, web_search, ast_grep); spawns scout.
- `scout` agent: `model: "@smol"` (fast model), `read-summarize: false` — the correct agent for pure read-only research.
- `@slow` priority chain: gpt-5.x/codex models → opus-4.x → pro. `@smol`: cerebras glm → gemini flash-lite/flash → haiku/mini.
- `model:` frontmatter accepts CSV/array = PRIORITIZED list: first available wins; the rest become retry-fallback candidates ONLY (executor.ts) — NOT quality escalation. `["@smol", "sonnet"]` means "sonnet only if smol errors/unavailable", never "escalate to sonnet when findings look serious". There is no built-in escalate-on-findings; that must be orchestrated (see Fix 5).
- Measured on this user's machine (transcripts, older config): 8 reviewer runs took 7m18s–10m42s each on claude-sonnet-5; opus-5:max will be at least that. The ~4m28s figure from the agent's self-report is the low end.

## User-authored task agents (tldr, pr, recipes)

Add a custom agent role by dropping `<name>.md` in `~/.omp/agent/agents/` (user scope
overrides bundled). Frontmatter: required `name` + `description`; optional `tools`
(CSV/array; `yield` auto-added), `model` (one/CSV/array = prioritized, role aliases like
`@smol`/`@slow` expand through `modelRoles`), `read-summarize: false` (verbatim reads for
summarizers), `prewalk`, `advisor`. Discovered at session start / task dispatch. Role
aliases inherit `modelRoles.default` before their own chain — pin every role when the
default is premium.

Working examples (built 2026-08-26; model set to the cheap/delegated tiers):
- **`tldr`** — non-interfering TL;DR role. Two parts: (a) a read-only agent
  `~/.omp/agent/agents/tldr.md`, `model: ["@smol","anthropic/claude-haiku-4-5"]`,
  `read-summarize: false`, prompt = one-line TL;DR + `| Aspect | BEFORE | AFTER |` table
  (≤15-word cells, concrete facts, ~25 lines, no prose dump); (b) a small omp extension
  (package `"omp":{"extensions":["extensions/tldr.ts"]}`) that hooks `message_end`, word-counts
  the final assistant reply, and over a threshold (env `TLDR_THRESHOLD_WORDS`, default 120)
  injects a **non-interfering, user-visible hint** — `pi.sendMessage({customType, content,
  display:true}, {triggerTurn:false})` (verified call in `modes/controllers/tan-command-controller.ts`)
  — plus an `input` hook that turns `/tldr`/`tldr: <q>` into a `{text}` input replacement
  routing summary through the tldr agent. Install plugin: `omp plugin install <path>`; copy
  `agents/tldr.md` into `~/.omp/agent/agents/`. Verify: `omp plugin list`/`omp plugin doctor`
  clean; RPC smoke `available_commands_update` shows the `/tldr` command with
  `"source":"extension"` and no `Extension "..." error`.
- **`pr`** — PR-description writer. Read-only agent `model: ["anthropic/claude-sonnet-5","@slow"]`,
  `tools: read, grep, glob, bash, write, lsp, ast_grep`; prompt = first `read`
  `/Users/laansdole/.agents/skills/writing-pr-descriptions/SKILL.md` (3-line lead verdict/price/call,
  tables-only, one `### <contract surface>` per surface, `Tests`, `Verification`=rerun gates,
  `Notes for review`; every cell ≤15 words; diff vs MERGE-BASE not the base tip; rerun gates;
  deliver to a gitignored file; never open the PR, stop at the file, fact-check quoted symbols).

General recipe for a new role: match the cheapest model that does the job (summarizers →
`@smol`; reviewers → `@slow`/opus; writers → sonnet), keep summarizer agents read-only,
and make any auto-trigger deterministic (code hook) not dependent on the main model's
judgment — that is why a rules-prompts extension like i-have-adhd fails to fix over-explaining.

## The slowness pattern (over-serialization)
- Typical flow: worker implements → reviewer reviews → main agent `hub wait`s on the reviewer. Reviewer = Opus-class model running a rigorous procedure (git diff → full file reads → LSP → optional scout spawn → incremental findings) — 4–5 min is realistic, not anomalous.
- Main agent idling behind a READ-ONLY reviewer = pure dead time. The framework prompts forbid it (`task.md`: "NEVER shrink or serialize a batch to avoid file overlap", "One-pass: Prefer agents that investigate AND edit in one pass") but it is unenforced prompt-level guidance — Opus can and does serialize.
- worker → reviewer → fix chains are inherently serial per stage; overlap independent work with the review window.

## Diagnosis recipe (user reports "agent is stuck / taking forever")
1. "Still Running" frame ≠ stall. Snapshot progress with `hub jobs` (or check the task list) instead.
2. Identify the long job: which agent? `reviewer` = @slow = Opus → slow by design. `scout` = fast.
3. Check for serialization: is the main agent waiting on a read-only job while other work is pending? That is over-serialization, not a hang.
4. Check the ladder: back-to-back waits climb to 5-min blocks → looks exactly like a stall.
5. Fact-check the transcript before advising: `~/.omp/agent/sessions/<project-slug>/<session-id>/Task*Reviewer.jsonl` (and `*Implementer.jsonl`) record `message.model` + `timestamp` per subagent run — confirm which model actually ran and its wall time. This turned "4-5 min reviewer" into measured "7-11 min on sonnet-5" in one session.

## Fixes (in order of impact)
1. **Reviewer model override** (biggest win): copy the bundled `reviewer.md` to `~/.omp/agent/agents/reviewer.md`, change `model: "@slow"` → `"@smol"` or a concrete fast id (e.g. `anthropic/claude-haiku-4-5`). User agents override bundled ones. Same procedure, seconds instead of minutes.
2. **Bound the waits**: set `async.pollWaitDuration: "30s"` (fixed) so the TUI never parks on a 5-minute frame.
3. **Behavior rule** in the project's AGENTS.md: "Never `hub wait` on a read-only agent; do other independent work while background jobs run; batch parallel tasks."
4. **Structural**: overlap the reviewer with the next independent task instead of waiting on it.
5. **Two-tier review (conditional deep pass)** — answers "can I use both fast and deep models?": keep `reviewer` on `@smol` (triage every task), add a second agent `~/.omp/agent/agents/reviewer-deep.md` (copy of reviewer, `model: "anthropic/claude-sonnet-5"`), plus an AGENTS.md rule: "After a review result, if any finding is P0/P1 or overall_correctness=incorrect, spawn reviewer-deep on the affected files." The reviewer output schema (priority P0-P3, confidence, overall_correctness) is the branch hook. Caveat: this is prompt-level orchestration — as reliable as the model follows the rule. The single-model override (Fix 1) is the only structural option; the built-in advisor pairs EVERY review with a deep model (always-on, not conditional), so it does not implement escalation.

## Headless spawning (delegating from another agent, verified omp 17.3.4)
- omp supports non-interactive runs: `omp -p` / `--print` = "process prompt and exit".
  Combined with `--cwd <dir>` to set the workspace: `omp -p --cwd ~/Projects/foo "brief"`.
  Sessions are SAVED normally — resume later interactively with `omp -r` (by ID prefix,
  path, or picker) or `-c` to continue.
- From Hermes: spawn via terminal(background=true, notify_on_complete=true), monitor with
  process poll/wait, relay results. Don't run `omp -p` in a foreground terminal call — it
  can run 10-30+ min on a real task and the guard treats it as long-lived.
- **Output is buffered until exit**: piping `2>&1 | tail -N` means process poll shows NOTHING
  live — the report only appears when the process exits. Monitor progress via `git log
  --oneline` in the target repo instead (commits landing = real signal) plus `ls` of expected
  files. Expect ~1 task per 4-5 min on Opus-class models; a 5-task TDD plan ≈ 20-40 min.
- **Verify independently when it exits — the final report is a SELF-REPORT.** Re-run the lint
  + test suite yourself, curl live endpoints, confirm the branch and commit count. omp
  typically works on a feature branch (e.g. `feat/recordings-api-backend`) per repo rules;
  don't expect changes on main. The user's rule is commit-locally-never-push, so also confirm
  nothing was pushed.
- **Expect plan bugs on first execution**: a plan written from code inspection will mismatch
  reality (FastAPI schema defaults are Query objects outside DI, whisperx diarize returns a
  DataFrame not a dict, config-helper signature differences, transformer input-shape
  requirements). The headless agent finding and fixing these is normal, not a failure — the
  final passing tests are the arbiter. Harvest those fixes back into the governing skill's
  pitfalls afterward.
- Briefs must be SELF-CONTAINED: the headless session has no conversation context. Include
  repo path, current state, the task, constraints, and verification steps. For this user,
  scope to ONE task at a time (plan-before-code workflow) — a big multi-part brief runs
  long and commits without the user watching. When executing a written plan file, pass the
  ABSOLUTE plan path and add: TDD requirement (failing test first, verify fail, implement,
  verify pass), "commit after every task with the plan's exact commit message", "do NOT
  push", "do NOT modify the plan file", "work on a feature branch not main", and "report
  task statuses + test results + deviations at the end". For Flutter repos: "use `fvm
  flutter`, not bare `flutter`".
- Other relevant flags from `omp --help`: `--model` (fuzzy match), `--smol`/`--slow`/
  `--plan` role overrides, `--append-system-prompt`, `--mode text|json|rpc|rpc-ui`,
  `--no-session` (ephemeral), `--allow-home`.
- Related: upstream `pi` has the same `-p`/`--print` contract (omp is a fork), so this
  applies to pi-based delegations generally.

## Silent provider/model fallback when the Anthropic OAuth session expires

Symptom: an `omp -p` headless run fails with
`401 Insufficient balance ... opencode.ai/workspace/wrk_.../billing (type=CreditsError)`
or `agent turn ended with provider error ... Insufficient balance`.

This is NOT a billing problem to report to the user and NOT a config problem —
your `config.yml` `modelRoles.default: anthropic/claude-opus-5:xhigh` is fine.
Root cause (measured 2026-08-20): the Anthropic **OAuth session had expired/signed
out**, and omp silently fell back to the `opencode-go` provider's default model
(`kimi-k2.7-code`), which bills through the opencode.ai workspace credits — hence
the "insufficient balance" from a workspace the user never intends to pay.

Diagnosis (before touching anything):
1. Grep the failed run's session transcript for which model actually ran:
   `grep -o '"model":"[^"]*"\|"provider":"[^"]*"' ~/.omp/agent/sessions/<project-slug>/<latest>.jsonl | sort | uniq -c`
   — `"provider":"opencode-go"` + `"model":"kimi-k2.7-code"` = fallback happened.
   A healthy run shows `"provider":"anthropic"` + `"model":"claude-opus-5"`.
2. `opencode auth list` — no anthropic credential listed = signed out.
3. `~/.omp/logs/omp.YYYY-MM-DD.*.log` — "agent turn ended with provider error",
   provider `opencode-go`, is the smoking gun; there will be NO anthropic lines
   at all (omp never even tried it).

Fix: user re-logs in — `opencode auth login` → anthropic (e.g. "Successfully logged
in to anthropic as tony@folktale.io", credentials saved to `~/.omp/agent/agent.db`).
Then BEFORE re-dispatching the brief, verify the new session file's first assistant
message shows `provider: anthropic` — do not assume the re-login took effect, and
never report a billing-failed dispatch as done (worktree stays clean/unimplemented).


## Installing pi-format plugins/extensions (i-have-adhd, etc.)
- omp is a pi fork: upstream pi INSTALL.md instructions map 1:1 — `pi install <url>` ≡ `omp plugin install <url>` (`install` is an alias of `plugin install`). User scope is the default → installs into `~/.omp/plugins`, global to all projects.
- Workflow: `omp plugin install <url> --dry-run` first (shows resolution), then the real install, then verify with `omp plugin list` AND `omp plugin doctor` (expect "N ok, 0 warnings, 0 errors").
- Extensions import from `@earendil-works/pi-coding-agent` (upstream package names) even under omp — resolves fine in practice; only suspect a fork-package mismatch if a plugin fails to load after an omp update.
- Session-persistent extensions read always-on flag files via `PI_CODING_AGENT_DIR`: the fork EXPORTS `process.env.PI_CODING_AGENT_DIR = <its agentDir>` at profile init, before extensions load (bundle evidence), and pi-package `getAgentDir()` honors that var (i-have-adhd's own INSTALL.md: "If `PI_CODING_AGENT_DIR` is set, put `.i-have-adhd-always` in that directory instead"). So on omp the flag lives in `~/.omp/agent/.i-have-adhd-always`, NOT `~/.pi/agent/` (an earlier note claiming `~/.pi/agent/` even on omp was wrong for omp; keep `~/.pi/agent/` only for genuine upstream pi).
- Worked example (Aug 2026): `omp plugin install https://github.com/ayghri/i-have-adhd` → `i-have-adhd@0.1.0`, doctor-clean. Per-session toggle: `/i-have-adhd` (footer shows `● ADHD ON`), off with "stop adhd mode".

## Extension API divergence from upstream (verified omp 17.3.4)
- The fork's `sessionManager` (class `Mi` in the bun bundle) DROPPED upstream's `buildContextEntries()`; its equivalent is `buildSessionContext()`, which returns `{ messages, ... }` where custom messages are `{ role: "custom", customType, content, display, details, attribution, timestamp }` (built by `JQ()`). Upstream 0.80.7 has BOTH methods; `buildContextEntries()` returns tree entries where custom messages are `{ type: "custom_message", customType, ... }`.
- Symptom: third-party pi extensions written against upstream crash at session start with `ctx.sessionManager.buildContextEntries is not a function`. Fix pattern (applied to ayghri/i-have-adhd, Aug 2026): feature-detect — prefer `buildContextEntries()` if it exists and yields an iterable (try/catch), else `buildSessionContext().messages`; scan entries accepting both shapes (`type === "custom_message" || role === "custom"`), keying on `customType`.
- Caveat: `~/.omp/plugins/node_modules/*` is bun-managed (`~/.omp/plugins/package.json` git deps + `bun.lock`) — a plugin reinstall/update overwrites local extension patches; the fix must land upstream to be durable.
- Manifest discovery: omp reads package.json `"omp"` field FIRST with `"pi"` as fallback (`f?.omp ?? f?.pi`, `(h.omp ?? h.pi)?.extensions` in the bundle) — declare pi-package extensions under `"omp"` for omp, keep `"pi"` for upstream.
- Upstream outcome (Aug 2026): the minimal in-place shim PR was withdrawn as a duplicate; upstream kept the adapter approach (extensions/context-compat.ts — `buildSessionContext().messages` preferred, `buildContextEntries()` fallback, fail-closed on unsupported). Align local installs to the upstream direction; fail-open (`[]` → ruleset re-injected) is the more robust choice for an extension, but the kept adapter fails closed by design (flagged in review).
- Real-binary verification (strongest): `scripts/omp-rpc-extension-smoke.ts` — spawns `omp --mode rpc --no-session --adhd` WITHOUT `--no-extensions` so ambient discovery loads the plugin via the manifest, then asserts commands register and no extension error. Pitfalls: omp RPC ignores stdin EOF (kill the child or the harness hangs); a bare `reader.read()` blocks past any deadline (race it with a timer); strip API keys from the env.
- Full session-manager API surface (`class Mi` method list), the `Os()`/`JQ()` context-builder shapes, the minified-bundle extraction recipe, and the mock-harness verification pattern: `references/source-verified-mechanics.md` → "Extension API: session manager surface".

## Second brain over session transcripts (omp-episodic-memory)
- Installed 2026-08-31 (npm `omp-episodic-memory` 1.1.0, global → `~/.local/bin/omp-episodic`, `omp-episodic-mcp`). Local-first second brain: indexes raw `~/.omp/agent/sessions/**/*.jsonl` (incl. `omp -p` headless runs) into SQLite (`~/.local/share/omp-episodic-memory/index.db`) with FTS5 keyword + `sqlite-vec` MiniLM-L6-v2 embeddings; hybrid RRF retrieval; read-only toward omp state; no cloud/keys.
- Usage: `omp-episodic index` (incremental), `omp-episodic search "q"`, `omp-episodic recall <task...>` (token-budgeted context), `stats`, `extract`/`inbox`/`approve`/`reject` (derive decisions/gotchas/runbooks), `graph`, `context`.
- MCP: `omp-episodic-mcp` (stdio) tools search/read/recall_for_task/list_gotchas/get_project_context. Register in **user-scope** `~/.omp/agent/mcp.json` (NOT `~/.omp/mcp.json` — that path is ignored) as `{ "mcpServers": { "omp-episodic-memory": { "command": "omp-episodic-mcp", "args": [] } } }`. Verified: an `omp -p --smol` session then exposes the `search` tool and returns real hits.
- Pitfall: v1.1.0 CLI has NO `daemon` subcommand (README ahead of release); background loop = `omp-episodic watch` (or run `index` on cron/launchd). First-run downloads the MiniLM model via Transformers.js.
- Why it's the right pick for this user: local-first (cloud-averse), and it searches the exact transcripts the `omp -p` workflow already produces.

## Support files
- `references/source-verified-mechanics.md` — exact file paths, line-level evidence, and code locations from the oh-my-pi repo, so future sessions skip the re-clone.
- `references/extensions-and-custom-roles.md` — how to build user-scope omp extensions + task-agent roles (v18 verified): event surface, non-interfering `sendMessage(display:true, triggerTurn:false)`, the no-raw-LLM-in-extension rule, install + RPC-smoke verify, and the tldr/pr role recipes.
- `scripts/omp-rpc-extension-smoke.ts` — ambient RPC smoke probe: verifies an extension under `~/.omp/plugins` loads on the real omp binary (manifest discovery) and registers its commands.
