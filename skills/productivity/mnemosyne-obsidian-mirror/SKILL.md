---
name: mnemosyne-obsidian-mirror
description: "Use when mirroring Mnemosyne into Obsidian. Categorised."
version: 1.0.0
author: LaansDole
license: MIT
metadata:
  hermes:
    tags: [mnemosyne, obsidian, memory, cron, markdown, categorisation]
    related_skills: [obsidian, memory-ui, hermes-cron-script-watchers]
---

# Mnemosyne -> Obsidian memory mirror

A scheduled job copies Hermes' Mnemosyne memories into the Obsidian vault as categorised,
read-only notes, so the user can browse, search and link what Hermes remembers.
Mnemosyne stays the source of truth: the copy is one-way, and the database is opened read-only.

## When to Use

- "Show / browse my Hermes memories in Obsidian", "is the memory mirror up to date?"
- "Categorise my memories", "why is X under General?", "add a topic for Y".
- Setting up, refreshing, pausing or removing the mirror job.
- NOT for remembering or forgetting things. Use the Mnemosyne tools; the next mirror run picks
  the change up. Edits made in the mirrored notes are overwritten and never reach Mnemosyne.

## What it writes

Under `<vault>/Hermes Memory/`:
- `Hermes Memory Index.md` - totals plus links to every topic and type note.
- `Topics/<Topic>.md` - one note per topic, with memories grouped by type, newest first.
- `Types/<Type>.md` - one note per type, with memories grouped by topic.

Each entry shows the text, date, importance and Mnemosyne id. Every generated note carries
`generated_by: mnemosyne-obsidian-mirror` in its frontmatter. The script only rewrites or
deletes files with that marker, and it refuses to run if a hand-written note sits at a path it
needs. Unchanged notes are not rewritten, so Obsidian sync and backups see no churn.

Included: current curated memories (working memory except raw chat turns, consolidated copies
not already mirrored, canonical facts, triples), with superseded and expired rows dropped and
near-duplicates merged. Excluded by default: raw `conversation` turns and Mnemosyne's free-text
conversation summaries (noisy; `--include-summaries` adds them).

## Categorisation (two axes)

1. Type comes from the Mnemosyne `source` field, fixed in the script: preference/user ->
   Preferences, fact -> Facts, tool -> Tools and setup, task / task:progress -> Tasks and
   progress, insight -> Insights, skill_update -> Skill updates, triples -> Knowledge graph.
   Any other source becomes its own type (e.g. `paper_review` -> "Paper review").
2. Topic comes from the user's rules file, `$HERMES_HOME/mnemosyne-obsidian/categories.json`
   (template: `scripts/categories.example.json`). First match wins: a memory goes to the first
   topic whose `sources` contain its source, or whose `keywords` (case-insensitive substrings)
   appear in its text. No match -> General.

The rules file is the agent's job to maintain. When the user asks to categorise memories, or
General grows:
1. Run `--uncategorized` to list what fell into General.
2. Group those memories by project, domain or tool. Propose new topics or extra keywords to the
   user: short list, one line each, with the memories each would capture.
3. Edit the rules JSON (order matters: put specific topics before broad ones, e.g. a project
   before the tool it uses). Keep cross-cutting personal preferences in General unless the user
   wants a topic for them.
4. Run `--check` (shows the uncategorized count), then a normal run, and report the new counts.
Topic names must differ from type names, or the script stops with a collision error.

## Commands

Script: `~/.hermes/skills/productivity/mnemosyne-obsidian-mirror/scripts/mirror.py` (if the
skill lives elsewhere, `skill_view` returns its `skill_dir`).

```bash
python3 <script> --check          # resolved paths, rule count, memory and uncategorized counts
python3 <script> --uncategorized  # memories that land in General, for writing rules
python3 <script> --dry-run        # notes that would be written or removed; writes nothing
python3 <script>                  # refresh; prints one line only when something changed
```

Paths: vault from `--vault` or `OBSIDIAN_VAULT_PATH` (process env, then `$HERMES_HOME/.env`);
DB from `--db`, `MNEMOSYNE_DB` or `$HERMES_HOME/mnemosyne/data/mnemosyne.db`; folder with
`--folder` (default "Hermes Memory").

## Setup

1. Obsidian vault exists and `OBSIDIAN_VAULT_PATH` is set in `$HERMES_HOME/.env` (see the
   `obsidian` skill).
2. Copy `scripts/categories.example.json` to `$HERMES_HOME/mnemosyne-obsidian/categories.json`.
   Then build real topics from the user's data: run `--uncategorized` (with no rules, everything
   is General) and follow the categorisation steps above.
3. Cron scripts must be real files in `~/.hermes/scripts/` (symlinks are rejected). Create a
   wrapper `~/.hermes/scripts/mnemosyne_obsidian_mirror.py` with `write_file`:
   ```python
   #!/usr/bin/env python3
   import os, runpy, sys
   TARGET = os.path.expanduser("~/.hermes/skills/productivity/mnemosyne-obsidian-mirror/scripts/mirror.py")
   sys.argv[0] = TARGET
   runpy.run_path(TARGET, run_name="__main__")
   ```
4. Run the wrapper with `--dry-run`, then once for real, and open the index note.
5. Create the job with `cronjob_manage` action=create: `name="mnemosyne-obsidian-mirror"`,
   `schedule="0 3 * * *"` (daily; any time works), `no_agent=true`,
   `script="mnemosyne_obsidian_mirror.py"`, `deliver="local"` (no chat message; output lands in
   `~/.hermes/cron/output/<id>/`). No LLM runs, so it costs nothing.
6. Confirm the first run: `hermes cron list` shows `Last run: ... ok`. Give the user the job id
   and `hermes cron pause|resume|run <id>`.

## Pitfalls

- The mirror copies memories verbatim. Anything stored in Mnemosyne (dev passwords, tokens,
  personal details) lands in the vault in plain text. If the vault syncs to a cloud service or
  is shared, warn the user and either keep the mirror folder out of sync or remove the secret
  from Mnemosyne first.
- Mnemosyne's schema changes between major versions. The script reads only a few tables, skips
  any that are missing and opens the DB read-only. If counts suddenly drop to 0 after a
  `hermes update`, run `--check` and compare with `hermes mnemosyne stats`.
- Users edit mirrored notes and lose the edits. Say plainly that the folder is regenerated, and
  suggest linking to the mirrored notes from their own notes instead of editing them.
- Stale facts (e.g. a retired tool still listed as the preferred one) are Mnemosyne problems,
  not mirror problems. Fix them in Mnemosyne; the next run updates the note.
