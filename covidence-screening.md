# Covidence T&A Screening — Launch Cheat Sheet

Skill: `~/.hermes/skills/covidence-screening/`
Design spec: `docs/superpowers/specs/2026-07-18-hermes-covidence-screening-design.md`
Implementation plan: `docs/superpowers/plans/2026-07-18-hermes-covidence-screening.md`

## One-time per review

1. In Covidence, set the review to **single-reviewer mode** (Settings → Switch to single reviewer).
2. Edit `~/.hermes/skills/covidence-screening/CRITERIA.md` -- fill in PICO + inclusion/exclusion; remove the `<!-- DO NOT REMOVE` placeholder.

## Launch

```bash
# 1. Chrome with remote debugging
open -na "Google Chrome" --args --remote-debugging-port=9222

# 2. In Chrome, navigate to the review's Review Summary page.

# 3. Start Hermes
hermes -t browser chat
```

In the Hermes prompt:
```
/browser connect
run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false
```

## First-run ladder (do all three before full unattended)

1. Dry run on Demo review: `dry_run=true, max_refs=10`.
2. Single-ref live: `max_refs=1`.
3. Approve-first-N: `max_refs=10, approve_first_n=5`.

## Stop conditions

- `max_refs` or `max_time` hit.
- Daily cap (in `STATE.md`) hit.
- Queue empty.
- Approve-first-N `stop` response.
- CDP drop / login expired / 3 consecutive identical ref IDs.

## Audit trail

- Log: `~/.hermes/logs/covidence-screening-<session-id>.jsonl` (one line per tick).
- Maybe rationales are in the per-reference notes field in Covidence (visible in the UI).
- End-of-session summary is printed to the Hermes terminal.
