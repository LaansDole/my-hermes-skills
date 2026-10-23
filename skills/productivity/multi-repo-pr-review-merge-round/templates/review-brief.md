# Review + make mergeable: <owner/repo> PR #<A> [and stacked #<B>]

Working directory: <abs path to the agent's OWN worktree> (<branch, or DETACHED>).
The user's main checkout at <path> is OFF LIMITS (<why: untracked files / modified lockfile>).
Push authorization: <"pushing to origin <branch> IS AUTHORIZED" | "NO PUSH of any kind - upstream-facing branch">.
<If detached: push with `git push origin HEAD:<branch>` (normal push, no force).>

PRs:
- #<A> "<title>": <head> -> <base> (+adds/-dels, N files) <CONFLICTING?>
- #<B> "<title>": <head> -> <head of A> (stacked; the coordinator merges A, retargets B to main, merges B)

Repo notes: <fvm flutter only | uv run pytest tests/unit (CI command) | bun check, never tsc | PHI rules | read sibling repo X READ-ONLY for the JSON contract>

Tasks, in order:
1. Install deps (<cmd>). `git fetch origin <branches>`.
2. <If conflicting: `git merge origin/main` (MERGE, not rebase), resolve, commit.>
3. Review the full diff (`git diff origin/<base>...HEAD`): correctness, security, error handling, deleted-but-still-referenced code, config/lockfile consistency, test quality, repo conventions (read AGENTS.md/CLAUDE.md first).
4. Fix every Critical/Warning finding with focused conventional commits. Suggestions: fix if cheap, else list.
5. Gates: <exact test/lint commands>. Paste pass/fail counts. Prove pre-existing failures on origin/<base> in a temp `git worktree add --detach` you remove afterwards.
6. Push (per the authorization above).
7. <Stacked: then check out B, `git merge origin/<A-branch>` if A changed, review B's own diff, gates, fixes, push.>
8. Write the report to ~/.hermes/cache/merge-round/<tag>-REPORT.md: per PR: CRITICAL / WARNINGS / SUGGESTIONS / FIXED (sha + line) / GATES (commands + counts) / MERGE READINESS (yes/no + why). Print it too.

HARD RULES (verified by the parent coordinator afterwards):
- Work ONLY inside the working directory above.
- NEVER git rebase, git reset --hard on a pushed branch, git push --force, git stash, or delete branches.
- NEVER post GitHub comments/reviews/issues and NEVER merge PRs. The coordinator merges after verifying.
- Commits ARE requested (even if the repo says "never commit unless asked"). Never commit .pi/, .bun-cache/ or incidental lockfile churn.
- If a test exposes a REAL bug, fix the SOURCE in a separate labelled commit. Never weaken the test.
- Report deviations honestly. Say plainly what could not be verified. Never fabricate output.

<!-- CONTINUATION variant: prepend
# CONTINUATION (verified by the parent coordinator - do not re-diagnose)
An earlier run was cut off by a provider usage limit at <step>. On disk: <unpushed commit shas + subjects>, <uncommitted files>. Inspect `git log -3` / `git diff`, keep what is correct, commit, then continue from step <N>.
-->
