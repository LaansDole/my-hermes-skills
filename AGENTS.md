# AGENTS.md — oh-my-pi agent rules

## Review workflow (two-tier)

- Implementation and review go through task agents. The `reviewer` agent is the FAST triage pass — do not escalate its model.
- After a review result: if any finding is P0/P1, or `overall_correctness` is `"incorrect"`, spawn `reviewer-deep` on the affected files for a second pass. Otherwise accept the result and move on.
- `reviewer-deep` is slow and thorough; only spawn it when the triage pass warrants it, never by default.

## Parallelism

- NEVER `hub wait` on a read-only agent (`reviewer`, `reviewer-deep`, `scout`) while other independent work exists. Spawn independent tasks in parallel batches; only wait when the next step genuinely depends on the result.
- Skip project-wide validation (build/lint/test) inside task agents; run those once at the end in the main session.
- Decide cross-task contracts up front and state them in the batch context; do not let agents negotiate interfaces mid-flight.
