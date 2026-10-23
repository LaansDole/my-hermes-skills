# merge-round STATE (coordinator ledger - update after every round)

Provider/model: commandcode/gpt-6-sol:xhigh (gpt-6.1-sol = MODEL_NOT_IN_PLAN). 5-hour usage windows.
Goal: spend Command Code usage until 2026-10-31 on PR + worktree review/audit/merge.
Repos in scope: ~/Projects/research-harness (LaansDole/research-harness, push authorized),
~/Projects/medvoice-all/medvoice (medvoice-research/medvoice-service, main unprotected),
~/Projects/medvoice-all/medvoice-mobile (medvoice-research/MedVoice, main needs 2 approvals - NEVER --admin).
EXCLUDED: ~/Projects/medvoice-all/semif (third-party TheoLeeCJ/SemIf-OpenJev).

## Items (as of 2026-10-23 15:20 +07)

| tag | where | status | next |
|---|---|---|---|
| mv-service #6 | medvoice-service | MERGED 719ec21 (249 unit tests verified locally) | done |
| mv-service #7 | medvoice/.worktrees/review (detached) | partial: local merge c7a1ebc of #6 into #7 unpushed; uncommitted tests/unit/test_term_guard.py (+38). PR #7 base retargeted to main | continue review of #7 own diff, gates, push HEAD:feat/medical-term-guard; coordinator verifies (uv --python 3.12 pytest tests/unit) and merges |
| mv-mobile #46 | MedVoice | verified (28 pass/1 skip, analyze 172 = main baseline); BLOCKED by 2-approval protection | user decision; do not --admin |
| mv-mobile #47 | medvoice-mobile/.worktrees/review (detached) | partial: unpushed 8567d09 (repro test: result action hidden by tab bar) + uncommitted fix in recording_view.dart / recording_android_view.dart | finish fix, gates (fvm flutter test/analyze), push HEAD:feat/medical-term-guard; merge only after #46 merges |
| rh-pr7 | research-harness/.worktrees/pr7-web-ui | local merge 5b7ab78f3b of origin/main (unpushed); review not started | review, bun check, tests, push; coordinator merges PR #7 |
| rh-advisor | research-harness/.worktrees/advisor-wip-asides + advisor-judge-gate | 2 fix commits in A (fb10e73f31, bc79319328), A tests 518/0 pass; not yet cherry-picked to B | cherry-pick to B, test B, report. NEVER push (upstream PR can1357/oh-my-pi#14279) |

Briefs: ~/.hermes/cache/merge-round/<tag>.md and <tag>-cont.md (continuations). Lane logs: <tag>.log / <tag>-cont.log.
