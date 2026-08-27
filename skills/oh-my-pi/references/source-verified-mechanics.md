# Oh-My-Pi source-verified mechanics

Evidence gathered Aug 2026 by shallow-cloning github.com/can1357/oh-my-pi (main) and reading source. All paths relative to repo root. These locations let a future session verify or extend without re-cloning blindly.

## Repo identity
- can1357/oh-my-pi is a fork of earendil-works/pi (upstream "Pi agent harness", pi.dev). Internal packages: `@oh-my-pi/pi-agent-core`, `@oh-my-pi/pi-ai`, `@oh-my-pi/pi-tui`, `@oh-my-pi/pi-utils`, `@oh-my-pi/omptype`.
- Upstream earendil-works/pi has a subagent example extension (packages/coding-agent/examples/extensions/subagent/) but NOT the unified hub tool; the unified hub (merged irc/job/launch) is an oh-my-pi feature.

## hub wait — the race (packages/coding-agent/src/tools/hub/index.ts, #executeWait)
- Race legs: `runningJobs.map(j => j.promise)` + bus waiter leg (IrcBus.global().wait, no own timeout — race window governs) + `timeoutPromise` (windowMs) + abort promise (steering).
- Comment in source: "Returns on the FIRST settled job, the first matching message, window expiry, or abort — never 'when everything finishes'; the model re-issues to keep waiting."
- Message wins even a photo-finish race (dequeued message must not be lost — `busCancelled` sentinel prevents late losers rejecting).
- A message already buffered on the session satisfies the wait before anything is watched.
- `HubTool.interruptible` = `op === "wait"` (or `logs` with `follow: true`).
- Bare wait with no running peers → returns immediately ("No running background jobs to wait for."), never blocks a full message-timeout window.
- Explicit `ids` matching nothing visible → "No matching jobs found for IDs: ..." with `history://<id>` hints, never a hang.

## The "useless" frame (docs/tools/hub.md)
- "An all-running snapshot is flagged `useless` and rendered as a displaceable waiting frame that the next hub call supersedes." → the "## Still Running" the user sees during a healthy wait.
- Wait timeouts are normal results ("A wait timeout is a normal result (`waited: null` or an all-running snapshot flagged `useless`), never an error.").

## Poll window (packages/coding-agent/src/async/job-manager.ts)
- `POLL_WAIT_LADDER_MS = [5_000, 10_000, 30_000, 60_000, 300_000]`; `POLL_ESCALATION_RESET_MS = 60_000` (idle gap resets to floor). `nextPollWaitMs(ownerId, now)`.
- Setting `async.pollWaitDuration` (config/settings-schema.ts): `5s`/`10s`/`30s`/`1m`/`5m`/`smart` (default).
- `irc.timeoutMs` default 120_000; mailbox cap 100 msgs/agent; job retention ~5 min after settlement (then `agent://<id>` / `history://<id>` / `hub send`); manager max-running fallback 15; `async.maxJobs` 1..100.

## Agent definitions & model routing
- Bundled agents: `packages/coding-agent/src/prompts/agents/` — reviewer.md, scout.md, designer.md, librarian.md, security-reviewer.md, task.md, init.md, frontmatter.md.
- User agents: `~/.omp/agent/agents/*.md`; project agents: `.omp/agents/*.md`. Precedence (docs/task-agent-discovery.md): "Earlier extension roots override later extension roots, Claude marketplace plugins, and bundled agents." Bundled parse errors are fatal to discovery.
- reviewer.md: `model: "@slow"`, tools `read, grep, glob, bash, lsp, web_search, ast_grep`, `spawns: scout`. Findings via incremental `yield` sections `type: ["findings"]`; verdict fields `overall_correctness`/`explanation`/`confidence`; criteria: provable impact, actionable, unintentional, introduced-in-patch, no unstated assumptions, proportionate rigor; mandatory cross-boundary dispatch-point check; "Every finding MUST be patch-anchored and evidence-backed."
- scout.md: `model: "@smol"`, `thinking-level: medium`, `read-summarize: false`.
- Model resolution (packages/coding-agent/src/config/model-resolver.ts): `findSlowModel()` tries the SAVED model string FIRST, then `MODEL_PRIO.slow` chain (priority.json): `openai-codex/gpt-5.5 → gpt-5.4 → gpt-5.3-codex → gpt-5.x → codex → opus-4.8/4-8 → ... → opus-4.1 → pro`. `@smol` chain: cerebras zai-glm-4.7 → gemini-3.1-flash-lite → gemini-3.5-flash → haiku-4-5 → flash → mini.
- Implication: reviewer = user's saved model (Claude Opus 5 here) unless overridden. scout = fast model.

## task tool guidance (packages/coding-agent/src/prompts/tools/task.md)
- "Read-only research MUST use `agent: \"scout\"` (faster model)."
- "One-pass: Prefer agents that investigate AND edit in one pass."
- "Overlap is safe: Concurrent edits to the same files auto-resolve ... NEVER shrink or serialize a batch to avoid file overlap."
- "Every task MUST skip validation (build/lint/tests) — validating mid-flight blocks agents on each other's edits."
- Async job contract (task-async-contract.md): "No polling needed. Settled-job inspection: `hub jobs` | `hub wait` delivers its snapshot → no duplicate async-result." `completed` = successful yield/job exit, NOT artifact acceptance — verify claimed changes.

## Investigation route that worked (when web search rate-limits)
- GitHub API repo search via curl: `api.github.com/search/repositories?q=pi+coding+agent&sort=stars` — disambiguated the two "pi" projects instantly.
- Shallow clone + grep beats web search for framework internals: `git clone --depth 1` then read source/docs directly.

## Measured reference points
- ~4m28s on Claude Opus 5: the agent's self-reported single reviewer run (multi-file diff, read-only) — the low end.
- Independent measurement from the user's session transcripts (2026-07-25 session, older config): 8 reviewer runs (Task2–Task9Reviewer) took 7m18s–10m42s each, all on `claude-sonnet-5`. Current config runs Opus:max, so expect ≥ that. Treat 7–11 min (mid model) as the realistic review baseline, not a fault.

## Local fact-check route (no repo access needed)
- Config: `~/.omp/agent/config.yml` — this user's value: `modelRoles: default: anthropic/claude-opus-5:max`. The `:max` thinking suffix matters: slowest inference mode.
- Transcripts: `~/.omp/agent/sessions/<project-slug>/<session-id>/` — `Task*Reviewer.jsonl`, `Task*Implementer.jsonl`, `FinalReviewer.jsonl` are subagent runs. Each JSONL line: `message.model` = model that ran, `timestamp` = event time. First-vs-last timestamp = subagent wall span. This verifies which model actually ran (config may have changed since the session).
- Model resolution detail: `shouldInheritDefaultBeforePriority` (model-resolver.ts) — the slow/smol/designer roles PREPEND the configured `modelRoles.default` to their priority chain; so `@slow` = the user's default model unless the default itself is a role alias.

## model frontmatter semantics (docs/task-agent-discovery.md + task/executor.ts)
- `model` accepts one selector, CSV, or array: "Entries are tried in order after role aliases are expanded." First pattern resolving to an available (non-disabled-provider) model wins; the remaining candidates become retry-fallback selectors only (`buildSubagentRetryFallbackCandidates`, used on retry/error/fallback).
- Therefore an array is resilience fallback, NOT quality escalation. Conditional deep review must be orchestrated by the main agent (see SKILL.md Fix 5: two-tier review via reviewer-deep agent + AGENTS.md rule keyed on P0/P1 or overall_correctness=incorrect).

## Extension API: session manager surface (bundle evidence, omp 17.3.4)
The runtime is the minified bun single-file script `~/.bun/bin/omp` (~12.5 MB text). Grep counts are dispositive for API presence: `buildContextEntries` = **0 hits** (GONE), `getBranch(` ≈ 44 hits. The fork's session manager is `class Mi`. Extraction recipe (python over the bundle):
- Locate the class: scan backwards from a known method (e.g. `appendCustomEntry(` at ~6854601) for `class <name>{`; brace-match to the end; regex `(?:^|[;{},])\s*(?:async\s+)?(#?[A-Za-z_$][\w$]*)\s*\(` lists public methods (filter `if/for/while/...` keywords).
- Public API of `Mi` (relevant subset): `getCwd`, `getSessionId`, `getSessionFile`, `getSessionName`/`setSessionName`, `getBranch`, `getEntries`, `getTree`, `getEntry`, `getChildren`, `getLeafId`, `getLeafEntry`, `buildSessionContext`, `appendMessage`, `appendMessageToBranch`, `appendCompaction`, `appendCustomEntry`, `appendCustomMessageEntry`, `appendModelChange`, `fork`/`newSession`/`dropSession`/`restoreState`/`captureState`/`flush`/`close`. NO `buildContextEntries`.
- `buildSessionContext(i)` → `Os(entries, leafId, byId, options)`: walks root→leaf, honors compaction (drops entries before `firstKeptEntryId`; compaction entry becomes a summary message), and projects `custom_message` entries via `JQ(customType, content, display, details, timestamp, attribution)` = `{ role: "custom", customType, content, display, details, attribution, timestamp }`. `custom` entries are NOT projected into messages. Returns `{ messages, thinkingLevel, serviceTier, models, injectedTtsrRules, mode }`. Synchronous.
- Extension context: the runner's `createContext()` hands extensions `{ ui, mode, sessionManager, modelRegistry, ... }` — `sessionManager` is the same class instance (`F`) used everywhere.
- Upstream comparison anchors (installed in `~/.omp/plugins/node_modules/`): `@earendil-works/pi-coding-agent/dist/core/session-manager.d.ts` — upstream `SessionManager` has BOTH `buildContextEntries(): SessionEntry[]` (tree entries; custom messages are `{ type: "custom_message", customType, ... }`) and `buildSessionContext(): SessionContext`; `@earendil-works/pi-agent-core/dist/harness/messages.d.ts` — `CustomMessage` = `{ role: "custom", customType, content, display, details, timestamp }` (identical shape to the fork's `JQ` output).
- Extension-compat fix pattern (applied to ayghri/i-have-adhd, Aug 2026): feature-detect in a `getContextEntries(ctx)` shim — prefer `buildContextEntries()` if present AND iterable (wrap in try/catch to tolerate stubs), else `buildSessionContext().messages ?? []`, else `[]`; scan accepting both shapes (`entry.type === "custom_message" || entry.role === "custom"`), keying on `customType`. Outcome: the minimal shim PR (#116) was withdrawn as a duplicate; upstream kept the adapter approach (PR #115: `extensions/context-compat.ts` — `buildSessionContext().messages` preferred, `buildContextEntries()` fallback, FAIL-CLOSED on unsupported manager). Fail-open (`[]` → ruleset re-injected, self-healing) is the safer choice for an extension — a throw at `session_start` is the crash class being fixed.

## Extension discovery & manifest (bundle evidence)
- omp scans `~/.omp/plugins/node_modules/*/package.json` for extension manifests. Reads `"omp"` FIRST, `"pi"` fallback: `f?.omp ?? f?.pi` (plugin metadata), `Y.omp || Y.pi` (package scan), `(h.omp ?? h.pi)?.extensions` (extension-path discovery). Declare `"omp": { "extensions": [...] }` for omp packages; keep `"pi"` for upstream.
- `PI_CODING_AGENT_DIR`: at profile init the fork sets `process.env.PI_CODING_AGENT_DIR = xh.agentDir` BEFORE extensions load. pi-package `getAgentDir()` honors that var (i-have-adhd INSTALL.md contract: "If `PI_CODING_AGENT_DIR` is set, put `.i-have-adhd-always` in that directory instead"), so on omp agent-dir-relative paths resolve to `~/.omp/agent`, NOT `~/.pi/agent`. A temp-dir `PI_CODING_AGENT_DIR` does NOT isolate the fork (it re-exports its own agentDir).

## Real-binary RPC smoke (strongest verification for extension changes)
- Ambient discovery path (the one that surfaces load-time errors): `omp --mode rpc --no-session --adhd` WITHOUT `--no-extensions`. RPC emits JSONL events; watch for `available_commands_update` (contains registered slash-command names) and `extension_ui_request`/`setStatus` events (`statusKey` + `statusText`, e.g. `i-have-adhd` → `● ADHD ON`). A load-time extension error prints `Extension "<path>" error: ...`. `session_start` fires during session init, so the extension's startup path (restoreState → syncContext) is exercised.
- Isolated variant (no ambient deps): `--no-extensions -e <pluginRoot>` loads only the given extension root (this is what i-have-adhd PR #115's `scripts/check_pi_extension.py --runtime omp` does).
- PITFALLS: (a) omp RPC IGNORES stdin EOF — it keeps running after stdin closes; you MUST kill the child (`proc.kill()`) before awaiting exit, or the harness hangs forever. (b) A bare stream `reader.read()` blocks past any deadline — race it with a timer (`Promise.race`) so the loop can time out. (c) For isolated runs, strip `*_API_KEY` env vars + `ANTHROPIC_AUTH_TOKEN`/`OPENAI_ACCESS_TOKEN`, set `PI_SKIP_VERSION_CHECK=1` and `PI_TELEMETRY=0`.
- Reusable probe: `scripts/omp-rpc-extension-smoke.ts` (args: command names to expect; `--status-key`/`--status-text` optional asserts; kills the child on completion).
- Verification pattern that works: a bun harness that imports the ACTUAL extension file and drives it with a mocked `ExtensionAPI` + a fork-shaped session manager (`getBranch` + `buildSessionContext`, no `buildContextEntries`) and an upstream-shaped one; 32 checks across session_start / /command / session_compact / input handlers (no-throw, single injection, no dup on resume, re-inject after compaction, disabled-notice ordering, `--flag` default). Needs `node_modules` resolution — a temporary symlink `~/<repo>/node_modules → ~/.omp/plugins/node_modules` works for both tsc and bun; remove after.
