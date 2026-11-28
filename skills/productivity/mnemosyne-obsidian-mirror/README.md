# mnemosyne-obsidian-mirror

Daily one-way copy of Hermes' Mnemosyne memory into an
Obsidian vault, as categorised read-only notes (`Hermes Memory/` folder: an index, one note per
topic, one note per type). Mnemosyne stays the source of truth; nothing is written back.

## Install

1. Symlink or copy this folder to `~/.hermes/skills/productivity/mnemosyne-obsidian-mirror`.
2. Set `OBSIDIAN_VAULT_PATH` in `~/.hermes/.env`.
3. Copy `scripts/categories.example.json` to `~/.hermes/mnemosyne-obsidian/categories.json` and
   edit the topics (or ask Hermes to build them from your memories).
4. Ask Hermes to "set up the Mnemosyne Obsidian mirror". `SKILL.md` has the wrapper and cron steps.

Requirements: Python 3.9+, stdlib only; Mnemosyne as the active Hermes memory provider.

## Run by hand

```bash
S=~/.hermes/skills/productivity/mnemosyne-obsidian-mirror/scripts/mirror.py
python3 $S --check          # paths and counts
python3 $S --uncategorized  # memories with no topic yet
python3 $S --dry-run        # preview
python3 $S                  # refresh
```

Tests: `python3 -m unittest tests.test_mnemosyne_obsidian_mirror` from the repo root.
