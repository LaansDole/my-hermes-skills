# session-handoff

Compress a Hermes session into a durable handoff record: a markdown summary, a machine-readable task index, and native Apple Reminders for follow-up. A companion cron job (`session-handoff-daily`) picks up leftover tasks each morning.

## What it does

- **Capture mode** (in-session, user-triggered): summarize the session + TODOs → handoff file, `tasks.json` entry, Apple Reminder in the `Hermes Follow-up` list (default due: next day 09:00, or `in N days` / a specific date).
- **Review mode** (cron): reads `tasks.json`, ensures every pending task due today/overdue has an open Reminder, syncs completions back, and reports a leftover digest.

## Setup

1. Install the CLI bridge: `brew install steipete/tap/remindctl`
2. Grant access: `remindctl authorize` (approve the macOS prompt)
3. Symlink into Hermes: `ln -s <repo>/skills/session-handoff ~/.hermes/skills/session-handoff`
4. Create the cron job (if not present):

```
hermes cron create "0 9 * * *"
```

then edit the job's prompt to run the skill in review mode (see SKILL.md), or recreate via the `cronjob` tool with `skills: ["session-handoff"]`.

## Runtime data

- `~/.hermes/session-handoffs/` — handoff `.md` files + `tasks.json`

## Customizing the cadence

- Change the cron time: `hermes cron edit <id>` (e.g. `0 21 * * *` for 9 PM).
- Per-task due dates: say "remind me in 3 days" / "on Friday" when triggering the skill.
