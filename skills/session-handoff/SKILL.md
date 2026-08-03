---
name: session-handoff
description: Use when ending or pausing a session, switching between sessions, or asked to save/compress session state with TODOs - compresses the current session into a handoff file, updates a task index, and creates Apple Reminders for follow-up. Also used by the daily reminder cron in review mode to pick up leftover tasks.
version: 1.1.0
metadata:
  hermes:
    tags: [session, handoff, todo, reminders, macos, productivity, cron]
    requires_toolsets: [terminal, file]
---

# Session Handoff

## Overview

Compress the current Hermes session into a durable handoff record so work survives across sessions. Three artifacts:

1. **Handoff file** — a markdown summary of what the session was about, what's done, what's next.
2. **Task index** — `~/.hermes/session-handoffs/tasks.json`, the machine-readable source of truth the daily cron reads.
3. **Apple Reminders** — native macOS reminders in the `Hermes Follow-up` list, so follow-ups alert on the Mac (and iCloud devices) at their due time.

A daily cron job (`session-handoff-daily`) runs the skill in **review mode**: it picks up leftover tasks, makes sure each has an open reminder, and reports a digest.

## When to Use

- User says "save session", "handoff", "compress", "what's next", "I'm switching sessions", "remind me about this later", or is about to end/close a session.
- User asks to capture TODOs with a follow-up reminder ("remind me tomorrow / in 3 days / on <date>").
- Cron job runs the skill in review mode (see below).

## Store

- `~/.hermes/session-handoffs/` — handoff files: `YYYY-MM-DD-HHMM-<slug>.md`
- `~/.hermes/session-handoffs/tasks.json` — task index (single source of truth for the cron)

## Capture Mode (in-session, user-triggered)

### 1. Gather context
- Read the current task list: `todo` (no args).
- Summarize from in-session context: goal, status, completed work, in-progress work, blockers, decisions, key files/commands.
- If the session is long and context feels incomplete, supplement with `session_search` (browse/query) for the current session's recent messages.

### 2. Determine due dates
- Default: **tomorrow 09:00**.
- "remind me in N days" → today + N days at 09:00.
- "remind me on <date>" or "at <time>" → that date/time.

### 3. Write the handoff file
`write_file(path="~/.hermes/session-handoffs/YYYY-MM-DD-HHMM-<slug>.md", content=...)` using the template below.

### 4. Update tasks.json
For each TODO / next step:
- Normalized title = lowercase, stripped of surrounding whitespace.
- If an open task (`status: "pending"`) with the same normalized title already exists → skip (dedupe).
- Otherwise append: `{"id": "<short-slug>", "title": "<title>", "session": "<handoff filename>", "created": "YYYY-MM-DD", "due": "YYYY-MM-DD HH:mm", "status": "pending"}`.
- Keep the file valid JSON.
- **IMPORTANT: the title stored in tasks.json MUST exactly match the reminder title created in step 5** (same casing, same punctuation). The cron's review mode matches titles verbatim against `remindctl list` — a case difference looks like "missing" and triggers duplicate reminders. Either lowercase both or title-case both; never mix.

### 5. Create Apple Reminders
- Find the list's ID first — **do NOT rely on `--create` being idempotent** (it is not on remindctl 0.3.2: it creates a duplicate empty list, which then makes every name-based `add` fail with "matches multiple lists"):
  ```bash
  remindctl list --json | python3 -c "import sys,json; [print(l['id']) for l in json.load(sys.stdin) if l['title']=='Hermes Follow-up']"
  ```
  - If exactly one ID: `HF_LIST_ID=<that id>`.
  - If none: create it, then re-list to capture the ID.
  - If more than one (a stray duplicate exists): use the one that already holds reminders (or the oldest creation date); the empty duplicate must be removed manually in Reminders.app — remindctl has no list-delete command.
- For each NEW task: `remindctl add --title "<title>" --list-id "<HF_LIST_ID>" --due "<YYYY-MM-DD HH:mm>"` — always a concrete date string (see pitfall 6). Using `--list-id` (not `--list`) sidesteps the name-ambiguity failure entirely.
- Skip any task whose title already has an open reminder, comparing **case-insensitively** (check `remindctl list "Hermes Follow-up" --json`).
- If the user asked for notes as well ("also save to Notes"), create an Apple Note via `memo notes -a "<title>"`. Default: skip — the handoff markdown files are the notes.

### 6. Report
"Handoff saved to <path>. N new reminder(s) in Hermes Follow-up, due <dates>."

## Review Mode (daily cron, ~09:00)

1. Read `~/.hermes/session-handoffs/tasks.json`; select tasks with `status == "pending"`.
2. For each task with `due <= now` (due today or overdue): ensure an open reminder exists — compare titles **case-insensitively** against `remindctl list "Hermes Follow-up" --json`; if missing, create it with `--due "<today's date YYYY-MM-DD> 09:00"` (always a concrete date string — see pitfall 6). Use `--list-id` for the add, resolved exactly as in capture-mode step 5.
3. Sync completions: completed reminders stay visible in `remindctl list "Hermes Follow-up" --json` with `"isCompleted": true` — for any pending task whose matching reminder shows `isCompleted`, set its `status` to `"done"` in tasks.json.
4. Reply with a digest: count + list of leftover tasks (due today / overdue first). If nothing pending, reply "No pending handoff tasks."

## Reminder Targets (hard rule)

**Apple only.** Default target is Apple Reminders (`remindctl`). Apple Notes (`memo`) and Apple Calendar are acceptable alternates if the user asks. **Never** use Jira, Atlassian, or any external task-tracking service for these reminders — the whole pipeline is native macOS (Reminders/Notes/Calendar) and must stay that way.

## Handoff Template

```markdown
# Handoff: <session title> — <date>

## Goal
<one sentence>

## Status
<done / in progress / blocked — one line>

## Completed
- <what got done>

## Next Steps (TODOs)
- [ ] <actionable task> (due: <date>)
- [ ] ...

## Open Questions / Blockers
- <anything a fresh session needs to know>

## Key Files / Commands
- <paths, commands, URLs>
```

## Common Pitfalls

1. **Vague TODOs.** A fresh session has zero context. "Implement X in file Y using Z" beats "continue the work". Each TODO must be actionable on its own.
2. **Duplicates.** Dedupe by normalized title in BOTH tasks.json and Reminders — never create two open reminders for the same task.
3. **Stale statuses.** tasks.json is the cron's source of truth; keep `status` current (cron syncs completions automatically, but don't leave tasks "pending" that you completed).
4. **Missed permission.** remindctl needs macOS + Reminders access: `brew install steipete/tap/remindctl`, then `remindctl authorize`.
5. **Overdue tasks stay open in Reminders** by design — the cron re-surfaces them daily until completed.
6. **Date-format trap:** `remindctl` rejects date words combined with times — `--due "today 09:00"` fails with "Invalid date". Always pass a concrete string: `--due "2026-08-04 09:00"`. Bare date words (`today`, `tomorrow`) work only without a time.
7. **Cron must run MCP-free.** The `session-handoff-daily` cron job MUST include `no_mcp` in its `enabled_toolsets` (`[terminal, file, skills, no_mcp]`). Hermes' scheduler otherwise unions every globally-enabled MCP server — e.g. a Jira/Atlassian MCP — into the job's toolsets, and the cron session hangs connecting to it, freezing the whole CLI session. `no_mcp` strips all MCP servers from the job.
8. **`--create` creates duplicates (remindctl 0.3.2).** `remindctl list "Name" --create` is NOT idempotent — it creates a second, empty list when one already exists. Then every name-based `remindctl add --list "Name"` fails with `matches multiple lists`. Always resolve the list ID first and use `--list-id` (capture-mode step 5). If a stray duplicate already exists, it must be deleted manually in Reminders.app — remindctl has no list-delete command. Name-based *reads* (`list --json`) still work fine with duplicates; only `add` breaks.
9. **Title case matters across the pipeline.** tasks.json titles must match reminder titles exactly (capture step 4), and the cron's presence check is case-insensitive (review step 2). If these drift, the cron creates duplicate reminders for tasks that already have them.

## Verification Checklist

- [ ] Handoff `.md` exists in `~/.hermes/session-handoffs/`
- [ ] `tasks.json` is valid JSON and contains the new tasks with `status: "pending"`
- [ ] `remindctl list "Hermes Follow-up"` shows one reminder per new task
- [ ] Cron `session-handoff-daily` picks the tasks up (check `hermes cron list` / saved output)
