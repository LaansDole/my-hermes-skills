# Has oh-my-pi adopted Pi 1.0 and Pi Durable?

- **Date:** 2026-10-15
- **Scope:** Whether can1357/oh-my-pi (omp) has adopted Earendil's Pi 1.0 release and the experimental Pi Durable package announced 2026-10-01.
- **Method:** Earendil "Pi Durable" post fetched 2026-10-15; omp releases, commits, code, PRs and issues queried via `gh` (GitHub search + API) on 2026-10-15. All findings are from these sources; nothing was measured locally.

---

## Verdict

No. omp has not adopted either one, and it should not rebase onto Pi 1.0, but it should keep closing Pi 1.x extension-compatibility gaps and track Pi Durable's design for its own durability proposals (see "Should omp adopt them?"). It has not rebased onto Pi 1.0 and does not use Pi Durable. omp is still a hard fork with its own version line (v18.11.0, released 2026-10-14). Its only link to Pi 1.x is a compatibility shim, so extensions written for upstream Pi 1.x can load in omp. A repo search for `pi-durable` returns no code. omp's own durability work is separate session-persistence hardening, plus two open proposals.

---

## Status

| Item | omp status | Evidence |
| --- | --- | --- |
| Pi 1.0 core (rebase / dependency) | Not adopted | Releases are v18.x (v18.11.0, 2026-10-14). The fork keeps `@oh-my-pi/*` packages and maps `@earendil-works/*` imports onto them (docs/porting-from-pi-mono.md). |
| Pi 1.x extension compatibility | Partial, shim only | PR #14909 (merged 2026-10-10) ports upstream pi 1.0.2/1.1.0 root exports (`getCurrentSystemMessage`/transcript utils, `compositeTuiLine`, `parseSkillBlock`) into the legacy shim. The PR lists gaps that are still open. |
| Pi Durable (`@earendil-works/pi-durable`) | Not adopted | Code search for `pi-durable` returns no files. Commit hits are unrelated session-durability fixes. |
| Durable-harness ideas, done natively | Proposals only | Issue #14386 (durable connection recovery and automatic task continuation, OPEN, 2026-10-06). Issue #6947 (session-durable workflow DAGs, OPEN). |
| Session crash durability (omp's own) | Shipped, ongoing | For example, PR #11560 (stale rewrites no longer erase durable turns, 2026-09-15) and 6c84a8bb (completed entries survive crashes). |

## Findings

1. Pi 1.0 and Pi Durable shipped together on 2026-10-01. Pi Durable is a separate harness framework of about 15k lines, with SQLite, JSONL and in-memory storage. It covers long-running and multi-surface agents and is explicitly "not a replacement" for the Pi coding agent (Earendil post).
2. omp treats upstream Pi as a source of features to port, not as a base to track. Examples are PR #12699 (cache-warming strategy, 2026-09-27) and PR #14909 (1.x shim gaps). Upstream 1.0 code is not merged wholesale.
3. Because Pi Durable is a separate package and not part of the coding agent, omp would have to integrate it on purpose. There is no PR or issue proposing that. The nearest item is native proposal #14386.
4. What this means in practice: Pi 1.x extensions (for example, pi-optchat pinned to pi 1.0.2) increasingly load in omp. Pi Durable features such as persistent storage backends, multi-human steering and remote execution environments are not available in omp.

## Should omp adopt them? (analysis)

Recommendation: omp should keep porting selectively rather than rebase onto Pi 1.0. It should not take Pi Durable into its core now, but it could support Pi Durable as an optional add-on.

| Change | Recommendation | Reasoning |
| --- | --- | --- |
| Rebase onto Pi 1.0 | No | omp has diverged into its own v18 line with its own packages, Rust natives, metaharness and auth gateway (repo layout, release notes). A rebase would mean rewriting most of omp. Its existing approach (porting doc, cherry-picks like #12699) already pulls in upstream improvements piece by piece. |
| Pi 1.x extension compatibility | Yes, keep closing the gaps | Pi 1.0 is described as a stable foundation (Earendil post), so its extension API should change less often from now on. Covering it in the shim gives omp users the upstream extension ecosystem cheaply. PR #14909 shows the pattern works and lists the gaps still open. |
| Pi Durable as omp's core runtime | Not now | Earendil labels Pi Durable experimental and says it "does not replace" the coding agent. omp already has its own session durability (#11560, 6c84a8bb), and moving onto an experimental runtime would put at risk crash-safety work omp has already shipped. |
| Pi Durable ideas / optional integration | Yes, worth tracking | Pi Durable's features (storage backends, reconnecting from different surfaces, remote execution environments, multiple people steering one agent) match omp's open proposals #14386 and #6947. omp could borrow the design, or let Pi Durable host omp-compatible tools through an adapter. It shares pi-ai with omp, so integration is plausible (ASSUMPTION: the API surfaces are still compatible enough to adapt; not verified). |

Main risk of not adopting: Pi 1.x and omp keep drifting apart, so each new upstream feature costs more to port. Keeping the compatibility shim test-pinned (as #14909 does) keeps that cost visible and contained.

## Caveats

- GitHub code search covers only the default branch and may miss very recent commits. The commit search is keyword-based.
- This is a snapshot from 2026-10-15. omp releases nearly every day, so check again before relying on it.

## References

- Pi Durable (Earendil Engineering, 2026-10-01): <https://earendil.com/posts/pi-durable/>
- oh-my-pi repository: <https://github.com/can1357/oh-my-pi>
- oh-my-pi v18.11.0 release: <https://github.com/can1357/oh-my-pi/releases/tag/v18.11.0>
- PR #14909, bridge upstream pi 1.x shim gaps: <https://github.com/can1357/oh-my-pi/pull/14909>
- PR #12699, port upstream pi cache-warming: <https://github.com/can1357/oh-my-pi/pull/12699>
- Issue #14386, durable connection recovery proposal: <https://github.com/can1357/oh-my-pi/issues/14386>
- Issue #6947, session-durable workflow DAGs: <https://github.com/can1357/oh-my-pi/issues/6947>
- docs/porting-from-pi-mono.md: <https://github.com/can1357/oh-my-pi/blob/main/docs/porting-from-pi-mono.md>
