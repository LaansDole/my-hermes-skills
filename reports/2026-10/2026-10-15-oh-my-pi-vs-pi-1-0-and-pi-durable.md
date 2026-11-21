# Has oh-my-pi adopted Pi 1.0 and Pi Durable, and should it?

- **Date:** 2026-10-15
- **Report type:** Evidence review
- **Keywords:** oh-my-pi, omp, Pi 1.0, Pi Durable, hard fork, extension compatibility
- **Data collected:** Earendil "Pi Durable" post fetched 2026-10-15; omp releases, commits, code, PRs and issues queried via `gh` on 2026-10-15.

## Abstract

**Background.** Earendil released Pi 1.0 and the experimental Pi Durable package on 2026-10-01 [1]. oh-my-pi (omp), a fork of Pi, would gain upstream features or durability from adopting either, at some integration cost.
**Objective.** To determine whether can1357/oh-my-pi has adopted Pi 1.0 or Pi Durable, and whether it should.
**Methods.** The Earendil announcement was read, and omp's releases, commits, code, pull requests and issues were queried through `gh` (GitHub search and API). Nothing was measured locally.
**Results.** omp is a hard fork on its own version line (v18.11.0, released 2026-10-14) [2]. Its only link to Pi 1.x is a compatibility shim extended by PR #14909 so that upstream Pi 1.x extensions can load [3]. A code search for `pi-durable` returns no files. omp's durability work is native session-persistence hardening plus two open proposals [4, 5].
**Conclusions.** No: omp has adopted neither Pi 1.0 nor Pi Durable. It should not rebase onto Pi 1.0, but it should keep closing Pi 1.x extension-compatibility gaps and track Pi Durable's design for its own durability proposals.

## 1. Introduction

Pi is Earendil's coding agent; omp (can1357/oh-my-pi) forked from it and now releases on its own schedule. Pi 1.0 and Pi Durable shipped together on 2026-10-01. Pi Durable is a separate harness framework of about 15k lines, with SQLite, JSONL and in-memory storage; it covers long-running and multi-surface agents and is explicitly "not a replacement" for the Pi coding agent [1]. Whether omp picks these up affects which extensions its users can run and how durable its sessions are.

- **RQ1.** Has omp rebased onto or depended on Pi 1.0?
- **RQ2.** Has omp adopted Pi Durable, or built equivalent durability itself?
- **RQ3.** Should omp adopt either?

## 2. Methods

### 2.1 Sources and search strategy

The Earendil "Pi Durable" post [1] was fetched on 2026-10-15. On the same date, omp's releases [2], PR #14909 [3], issues [4, 5], porting doc [6], PR #12699 [7], and code and commits in the repository [8] were queried via `gh` (GitHub search + API). Search terms included `pi-durable` (code search) and durability keywords (commit search); the full query list was not recorded.

### 2.2 Evidence classification

- **Repository records:** releases, PRs, issues, docs, code and commit search results, observed directly via `gh` [2, 3, 4, 5, 6, 7, 8]. No software was run.
- **Vendor-reported:** Earendil's description of Pi 1.0 and Pi Durable [1].
- **Interpretation:** the adoption recommendations (Table 2) are the author's analysis; one untested premise is labelled ASSUMPTION.

### 2.3 Experimental setup

Not applicable; nothing was measured locally.

### 2.4 Analysis

Each candidate adoption path was checked for direct evidence (dependency, merged code, open PR or issue) in omp's repository.

## 3. Results

### 3.1 Adoption status (RQ1, RQ2)

Table 1. omp adoption status as of 2026-10-15 (repository records).

| Item | omp status | Evidence |
| --- | --- | --- |
| Pi 1.0 core (rebase / dependency) | Not adopted | Releases are v18.x (v18.11.0, 2026-10-14) [2]. The fork keeps `@oh-my-pi/*` packages and maps `@earendil-works/*` imports onto them (docs/porting-from-pi-mono.md) [6]. |
| Pi 1.x extension compatibility | Partial, shim only | PR #14909 (merged 2026-10-10) [3] ports upstream pi 1.0.2/1.1.0 root exports (`getCurrentSystemMessage`/transcript utils, `compositeTuiLine`, `parseSkillBlock`) into the legacy shim. The PR lists gaps that are still open. |
| Pi Durable (`@earendil-works/pi-durable`) [1] | Not adopted | Code search for `pi-durable` returns no files. Commit hits are unrelated session-durability fixes. |
| Durable-harness ideas, done natively | Proposals only | Issue #14386 (durable connection recovery and automatic task continuation, OPEN, 2026-10-06) [4]. Issue #6947 (session-durable workflow DAGs, OPEN) [5]. |
| Session crash durability (omp's own) | Shipped, ongoing | For example, PR #11560 (stale rewrites no longer erase durable turns, 2026-09-15) and 6c84a8bb (completed entries survive crashes). |

- omp ports upstream features selectively, for example PR #12699 (cache-warming strategy, 2026-09-27) [7] and PR #14909 (1.x shim gaps) [3]. Upstream 1.0 code is not merged wholesale.
- No PR or issue proposes integrating Pi Durable. The nearest item is the native proposal #14386 [4].
- Pi 1.x extensions (for example, pi-optchat pinned to pi 1.0.2) increasingly load in omp. Pi Durable features such as persistent storage backends, multi-human steering and remote execution environments [1] are not available in omp.

## 4. Discussion

### 4.1 Principal findings

RQ1 and RQ2: omp has not rebased onto Pi 1.0 and does not use Pi Durable. omp is still a hard fork with its own version line [2], treating upstream Pi as a source of features to port, not as a base to track. Because Pi Durable is a separate package and not part of the coding agent, omp would have to integrate it on purpose, and nothing suggests that is planned.

### 4.2 Comparison with prior work

Earendil positions Pi 1.0 as a stable foundation and Pi Durable as experimental [1]. omp's existing session durability (#11560, 6c84a8bb) and its open proposals #14386 and #6947 [4, 5] address overlapping goals natively rather than through Pi Durable.

### 4.3 Practical implications

RQ3: omp should keep porting selectively rather than rebase onto Pi 1.0. It should not take Pi Durable into its core now, but it could support Pi Durable as an optional add-on.

Table 2. Adoption recommendations (interpretation).

| Change | Recommendation | Reasoning |
| --- | --- | --- |
| Rebase onto Pi 1.0 | No | omp has diverged into its own v18 line with its own packages, Rust natives, metaharness and auth gateway (repo layout, release notes) [8, 2]. A rebase would mean rewriting most of omp. Its existing approach (porting doc, cherry-picks like #12699) [6, 7] already pulls in upstream improvements piece by piece. |
| Pi 1.x extension compatibility | Yes, keep closing the gaps | Pi 1.0 is described as a stable foundation (Earendil post) [1], so its extension API should change less often from now on. Covering it in the shim gives omp users the upstream extension ecosystem cheaply. PR #14909 shows the pattern works and lists the gaps still open [3]. |
| Pi Durable as omp's core runtime | Not now | Earendil labels Pi Durable experimental and says it "does not replace" the coding agent [1]. omp already has its own session durability (#11560, 6c84a8bb), and moving onto an experimental runtime would put at risk crash-safety work omp has already shipped. |
| Pi Durable ideas / optional integration | Yes, worth tracking | Pi Durable's features (storage backends, reconnecting from different surfaces, remote execution environments, multiple people steering one agent) [1] match omp's open proposals #14386 and #6947 [4, 5]. omp could borrow the design, or let Pi Durable host omp-compatible tools through an adapter. It shares pi-ai with omp, so integration is plausible (ASSUMPTION: the API surfaces are still compatible enough to adapt; not verified). |

The main risk of not adopting is that Pi 1.x and omp keep drifting apart, so each new upstream feature costs more to port. Keeping the compatibility shim test-pinned (as #14909 does) [3] keeps that cost visible and contained.

## 5. Limitations

- **Search coverage.** GitHub code search covers only the default branch and may miss very recent commits. The commit search is keyword-based, so an absence of hits does not prove an absence of work.
- **Staleness.** This is a snapshot from 2026-10-15. omp releases nearly every day, so check again before relying on it.
- **Untested compatibility.** The plausibility of a Pi Durable adapter rests on an unverified ASSUMPTION about API compatibility.
- **Single upstream source.** Pi Durable's scope and status come only from Earendil's announcement [1].

## 6. Conclusion

omp has adopted neither Pi 1.0 nor Pi Durable; it remains a hard fork that ports upstream features selectively and bridges Pi 1.x extensions through a shim. The sensible path is to keep extending that shim, not rebase, and to borrow from Pi Durable's design for omp's own durability proposals rather than adopt the experimental runtime.

## References

[1] Pi Durable (Earendil Engineering, 2026-10-01): <https://earendil.com/posts/pi-durable/>
[2] oh-my-pi v18.11.0 release (GitHub, 2026-10-14): <https://github.com/can1357/oh-my-pi/releases/tag/v18.11.0>
[3] PR #14909, bridge upstream pi 1.x shim gaps (can1357/oh-my-pi): <https://github.com/can1357/oh-my-pi/pull/14909>
[4] Issue #14386, durable connection recovery proposal (can1357/oh-my-pi): <https://github.com/can1357/oh-my-pi/issues/14386>
[5] Issue #6947, session-durable workflow DAGs (can1357/oh-my-pi): <https://github.com/can1357/oh-my-pi/issues/6947>
[6] docs/porting-from-pi-mono.md (can1357/oh-my-pi): <https://github.com/can1357/oh-my-pi/blob/main/docs/porting-from-pi-mono.md>
[7] PR #12699, port upstream pi cache-warming (can1357/oh-my-pi): <https://github.com/can1357/oh-my-pi/pull/12699>
[8] oh-my-pi repository (GitHub): <https://github.com/can1357/oh-my-pi>
