# omp v18: custom agent roles + extensions (verified 2026-08-26)

Build a passive, non-interfering omp capability (a summary/tldr affordance, an
always-on trigger, a PR-description writer) as user-scope files — NO omp source
fork, NO recompile. Confirmed against omp 18.0.4 source
(`src/extensibility/extensions/types.ts`, `runtime-init.ts`,
`modes/controllers/tan-command-controller.ts`) and the installed `i-have-adhd`
extension.

## Two mechanisms

1. **Task-agent role** — `~/.omp/agent/agents/<name>.md` (also `pr.md`, `tldr.md`
   exist here). Frontmatter: `name`, `description`, `tools` (CSV), `model` (list),
   `read-summarize: false`. Spawned by the `task` tool with `agent: "<name>"`.
   Cheap tier = `@smol`. Model via frontmatter `model:` list or
   `task.agentModelOverrides[agentName]`.
2. **Extension/plugin** — `~/.omp/plugins/<pkg>/` with
   `package.json` `"omp": {"extensions":["extensions/x.ts"]}` plus the `.ts`.
   Loaded automatically. Registered slash commands appear in the RPC
   `available_commands_update` event with `"source":"extension"`.

## Extension API (verified event surface + call shapes)

- `pi.on(event, handler)` names (relevant subset): `message_start/update/end`,
  `turn_start/end`, `agent_start/end`, `input`, `session_start`, `session_tree`,
  `session_compact`, `tool_call/result`, `after_provider_response`, `context`.
  Full list: `src/extensibility/extensions/types.ts`.
- `message_end` fires `{ type, message: AgentMessage }`. `AgentMessage.content`
  is a content-block array (`{type:"text",text}` blocks) or a string; for an
  assistant reply extract text where `role === "assistant"`.
- **Non-interfering user-visible note**: `pi.sendMessage({ customType, content,
  display:true }, { triggerTurn:false })` — surfaces text to the user WITHOUT
  starting a model turn (pattern used in `tan-command-controller.ts`).
  `display:false` injects for the model only (i-have-adhd ruleset). NOTE: command
  registration / RPC verified; interactive TUI rendering of a `display:true`
  custom card was not visually confirmed this session — fallback if it doesn't
  render cleanly is `ctx.ui.notify(...)`.
- `input` hook: return `{ text, handled? }` to REPLACE the user's input
  (`InputEventResult` — the canonical shape is `{text}`; i-have-adhd uses the
  legacy `{action:"transform"}`). Use to intercept `tldr: ...` / `/tldr`.
- `pi.registerCommand(name, {description, handler})`, `pi.registerFlag`,
  `pi.appendEntry`, `ctx.ui.notify`, `ctx.ui.setStatus`.

## The critical rule: NO raw LLM completion in an extension

`ExtensionContext.modelRegistry` is exposed BUT has **no raw completion call** —
it only resolves/authenticates models. So to produce LLM *output* (summaries,
descriptions) from a passive capability, spawn a cheap **task agent**
(`agent:"tldr"` on `@smol`) and let the main agent relay its output — do not
try to call a model directly inside the extension.

## Hard build constraint

Extension `.ts` MUST have **no runtime imports from `@oh-my-pi/*`** and no
`node:fs` / external / native ES modules — the compiled omp binary cannot resolve
them inside its bundle. Only TYPE imports from `@earendil-works/pi-coding-agent`
are allowed.

## Install + verify

- Install: `omp plugin install /abs/path/to/pkg` (links it).
- `omp plugin list`, `omp plugin doctor` → expect "N ok, 0 warnings, 0 errors".
- **RPC smoke** (strongest): run `omp --mode rpc --no-session </dev/null` as a
  background process, sample ~20s, kill, then grep the log for
  `available_commands_update` containing `{"name":"<cmd>",...,"source":"extension"}`
  and confirm NO `extension...error`. RPC ignores stdin EOF → kill after sampling.
- Task-agent file: copy to `~/.omp/agent/agents/<name>.md`; discovered at session
  start / next `task` dispatch.

## Example recipes (this box)

- **`tldr` role** (source `~/Projects/omp-tldr`, local, never pushed): `message_end`
  word-count (default >120, override env `TLDR_THRESHOLD_WORDS`) → emits the
  non-interfering hint card; `input` hook rewrites `tldr: <q>` and `/tldr` into a
  directive to spawn the `tldr` agent (`@smol`, read-only, tl;dr format).
  `autoGenerate` toggle exists but defaults OFF so the feature "does not interfere"
  (the user's hard constraint).
- **`pr` role** (`~/.omp/agent/agents/pr.md`): `model: ["anthropic/claude-sonnet-5","@slow"]`;
  reads the user's authoritative skill at `~/.agents/skills/writing-pr-descriptions/SKILL.md`
  first (3-line verdict/price/call lead + ≤15-word tables, diff-vs-merge-base,
  rerun gates, write to a gitignored file, NEVER open the PR).

## Pitfalls

- omp RPC processes keep running / ignore stdin EOF — sample the log then kill.
- Model `model:` arrays are availability fallback, not quality escalation.
- Never hand an implementer a plan whose code contains raw `...```...```...`
  fences in a shell-multiline prompt — it breaks `omp -p "$(cat ...)"` parsing;
  write the dispatch prompt to a file first.