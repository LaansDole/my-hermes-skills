# Changelog

## [1.1.0] - 2026-11-28

### Added
- Theming hooks: every generated note lists `cssclasses` (`hermes-memory` plus
  `hermes-memory-index|topic|type`), and each memory's meta line carries an
  `#importance/high|medium|low` tag after its importance score.

## [1.0.0] - 2026-11-28

### Added
- `scripts/mirror.py`: one-way, read-only mirror of Mnemosyne memories into an Obsidian vault
  (index, topic notes, type notes), with dedupe, superseded/expired filtering, marker-guarded
  writes and pruning, `--check`, `--dry-run`, `--uncategorized` and `--include-summaries`.
- Two-axis categorisation: type from the Mnemosyne source, topic from a user rules file
  (`scripts/categories.example.json`).
- Setup steps for a daily no-agent Hermes cron job.
