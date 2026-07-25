# Covidence Full-Text Retrieval: NotebookLM Discover Fallback — Design

## Context

`covidence-full-text-retrieval` (planned in `docs/superpowers/plans/2026-07-25-covidence-full-text-retrieval.md`, not yet implemented) retrieves full-text PDFs for references in Covidence's Full text review stage via three deterministic, keyless, DOI/ID-based lookups: Unpaywall, Semantic Scholar Graph API, arXiv direct. References none of the three can resolve get a note logged for manual follow-up.

This spec adds a fourth, AI-assisted discovery layer using NotebookLM's "Discover sources" feature (a Gemini-powered web search that recommends up to 10 sources for a described topic, launched by Google in April 2025) as a last-resort search before a reference is declared not-found. It does not change anything about Layers 1-3, the upload/note action policy, the safety rules, or any other part of the already-planned skill.

## Goal

Raise the hit rate on references that have no DOI, no arXiv ID, or whose DOI/arXiv lookups miss (e.g. because the OA copy isn't indexed by Unpaywall/Semantic Scholar) by trying one more, broader web search before giving up — using NotebookLM's own AI-mediated search rather than scraping a search engine ourselves.

## Non-goals

- No cookie-export hack, no headless separate script, no third-party NotebookLM API wrapper (`notebooklm-mcp-cli` / `nlm` CLI). The skill drives NotebookLM's real web UI directly through the same CDP-attached Chrome already used for Covidence.
- No notebook-per-reference or notebook-per-review. Exactly one NotebookLM notebook, named by the user-supplied research topic, shared across the whole review (and reused across sessions).
- No auto-login to NotebookLM/Google. If the tab isn't already authenticated, the skill stops and tells the user to log in themselves — same non-goal as Covidence SSO in the parent skill.
- Does not replace Layers 1-3. Never runs before them; never runs at all if `notebooklm_topic` is omitted.
- Does not touch any other existing NotebookLM notebook, and never deletes/renames/shares the one notebook it uses.

## Parameters (additions to `covidence-full-text-retrieval`)

- `notebooklm_topic` (string, optional, no default): human-readable label for the review's research topic, e.g. `"AI multi-agent depression screening review"`. Also the exact title used to find-or-create the shared NotebookLM notebook. **If omitted, Layer 4 is skipped entirely** — Layers 1-3 run as originally planned, and a miss on all three goes straight to `NOT_FOUND` with no NotebookLM tab ever opened. This keeps the base skill's behavior unchanged for anyone who doesn't want the NotebookLM dependency.
- `notebooklm_max_candidates` (int, default 3): how many of Discover's recommendation cards to evaluate for title-match, per reference, before declaring a Layer 4 miss.

## Prerequisites (additions)

- The user is already logged into `notebooklm.google.com` in the same Chrome instance Hermes is attached to via CDP (the one used for Covidence). No separate NotebookLM credential setup.
- If `notebooklm_topic` is provided but the NotebookLM tab redirects to a Google sign-in page, the skill does not attempt Layer 4 for the rest of the session: log "NotebookLM not authenticated, Layer 4 disabled for this session" once, and fall back to Layers 1-3 only for every subsequent reference (do not repeatedly retry a dead login).

## Architecture: tab management

The skill now coordinates two tabs on one CDP-attached Chrome:
- **Tab A (Covidence)** — the existing tab, unchanged role.
- **Tab B (NotebookLM)** — opened once, lazily, the first time Layer 4 actually fires (i.e. the first reference where Layers 1-3 all miss and `notebooklm_topic` is set). Stays open for the rest of the session; reused for every subsequent Layer 4 attempt.

Every action in the Screen Loop and Action Policy operates on Tab A by default. Layer 4 steps explicitly switch to Tab B, act, then switch back to Tab A before resuming the reference-block walk. Never issue a click/fill intended for one tab while the other is active — Hermes' tab-addressing (from `/browser connect`'s tab list) makes the target tab explicit on every call, not implicit from "whichever tab was last used."

## Notebook reuse (no persisted state)

The first time Tab B is opened in a session:
1. Navigate to the NotebookLM home page (the notebook list).
2. Scan for an existing notebook whose title exactly matches `notebooklm_topic`.
3. Found → open it. Not found → create a new notebook and set its title to `notebooklm_topic` exactly.

This lookup runs once per session (result cached in-memory as `notebook_ready` for the rest of the run) and is repeated fresh on the next session — nothing about the notebook's identity is written to `STATE.md` or any other file. If two sessions somehow ever created two notebooks with the same title (e.g. a race from two Hermes sessions running at once), that's a manual cleanup the user does in the NotebookLM UI; the skill does not attempt to detect or merge duplicates.

## Layer 4 discovery flow (per reference, only after Layers 1-3 miss)

Runs inside the existing Full-Text Discovery Step, as step 4a (renumbering the prior "Layer 3 arXiv direct" step's fallthrough target):

1. Switch to Tab B. Confirm `notebook_ready` (open the notebook from the reuse logic above if this is the first Layer 4 call this session).
2. Open **Discover sources** (the button next to "Add source" in the Sources panel).
3. Type a search query into the "Describe something you'd like to learn about" box: the reference's exact title, plus the first author's surname for disambiguation (e.g. `MAMA-Memeia! Multi-Aspect Multi-Agent Collaboration for Depressive Symptoms Identification in Memes Agarwal`). Submit.
4. Wait for the recommendation cards to render (each has a title and an AI-generated summary). Read up to `notebooklm_max_candidates` cards, best-ranked first.
5. For each candidate, in order:
   a. **Title-match check**: normalize both the candidate's title and the target reference's title (lowercase, strip punctuation/whitespace-collapse) and require high token overlap. Not a confident match → skip to the next candidate without adding it.
   b. Confident match → click the card's **Add** action to import it as a source into the notebook.
   c. Open the newly added source's "view original" affordance (NotebookLM shows this per-source, same external-link-icon pattern as Covidence's own DOI links). This opens the source's real URL in a new tab (Tab C, ephemeral). Read `location.href` from Tab C via `tab.evaluate(() => location.href)`, then close Tab C.
   d. That URL becomes `candidate_url`, `source=notebooklm`. Switch back to Tab A is deferred until validation is decided (see step 6) — validation itself runs over `terminal`, not either browser tab.
   e. Validate `candidate_url` exactly like Layers 1-3: `curl -sIL --max-time 20 "$candidate_url" | grep -i '^content-type:' | tail -1`, require `application/pdf`. Valid → discovery result is `FOUND` (`source=notebooklm`), stop trying further candidates. Invalid → continue to the next candidate (still added to the notebook as a byproduct source even though it didn't validate as a PDF — that's fine, it's still a relevant source for later human reading).
6. If no candidate among the first `notebooklm_max_candidates` validates: Layer 4 is a miss. Discovery result is `NOT_FOUND` overall (log which sources, if any, got added to the notebook despite not validating, so the not-found note can mention "N related sources were added to the NotebookLM notebook `<title>` even though no direct PDF was found").
7. Switch back to Tab A. Resume the Action Policy exactly as already specified: `FOUND` → download `candidate_url` via `curl`, verify size, upload via `tab.uploadFile` into the target Covidence reference block; `NOT_FOUND` → write the per-reference note (now also mentioning the notebook if sources were added there).

No new action-policy branching is introduced — Layer 4 only changes how `candidate_url`/`source` get produced, feeding the same download/upload/note logic Layers 1-3 already use.

## Safety rules (additions)

- Strict allowlist on Tab B: only the Discover-sources flow, the Add-source action, and opening a source's "view original" link, all confined to the one notebook resolved/created for `notebooklm_topic`. No deleting, renaming, or sharing that notebook; no touching any other notebook in the account; no removing a source once added (even one that didn't validate as a PDF — it stays as a byproduct research artifact).
- If Tab B ever navigates outside `notebooklm.google.com` (other than the deliberate, immediately-closed Tab C for reading a source's original URL), treat it the same as the parent skill's off-domain rule: stop Layer 4 for the rest of the session, log, and continue with Layers 1-3 only.
- Same never-touch-Include/Exclude, never-paywall-circumvention rules from the parent skill apply unchanged — Layer 4 only ever produces `candidate_url` values from sources NotebookLM itself surfaced via a legitimate web search; the sci-hub/libgen/annas-archive/z-lib domain blocklist check on `candidate_url` still applies to Layer 4 output too.

## Logging (additions)

Same JSONL schema as the parent skill (`ts`, `ref_id`, `ref_header`, `title`, `state`, `discovery`, `source`, `candidate_url`, `action`, `ok`), with `source` now able to be `notebooklm` in addition to `unpaywall`/`semantic_scholar`/`arxiv`/`none`. Add one additional field, `notebook_sources_added` (int, default 0): how many candidates from this reference's Discover search got added to the notebook regardless of whether one ultimately validated as a PDF — lets the end-of-session summary report "N byproduct sources landed in the NotebookLM notebook" even for otherwise-not-found references.

## Error recovery (additions)

| Failure | Detection | Recovery |
|---|---|---|
| NotebookLM tab not authenticated | Tab B navigates to a Google sign-in URL | Log once, disable Layer 4 for the rest of the session, continue with Layers 1-3 only. |
| Discover sources produces no cards / times out | No recommendation cards render within 20s of submitting the query | Treat as a Layer 4 miss for this reference (no candidates to evaluate); do not retry the same query. |
| "View original" doesn't open a new tab / URL unreadable | `tab.evaluate` on the expected new tab errors or times out | Skip this candidate, try the next one (up to `notebooklm_max_candidates`); if all fail, Layer 4 miss. |
| Notebook-list scan finds two notebooks matching `notebooklm_topic` | More than one exact-title match on the home page | Log a warning, use the first match, do not create a third. Surface this to the user in the end-of-session summary so they can clean up manually. |

## Self-review

- **Placeholder scan**: no TBD/TODO; every step names the concrete UI action or terminal command.
- **Consistency**: `candidate_url`/`source`/`FOUND`/`NOT_FOUND` vocabulary matches the parent skill's Full-Text Discovery Step and Action Policy exactly — Layer 4 is a drop-in producer of the same two fields, no new decision branches in the upload/note logic.
- **Scope**: bounded to one new fallback layer, tab management, and notebook reuse. Does not reopen or restate Layers 1-3, the upload mechanism, Loop Control, or the STATE.md/SETUP.md content already speced in the implementation plan — those are unchanged and will only get parameter/prerequisite additions when the plan is revised.
- **Ambiguity check**: "high token overlap" for title-matching is intentionally left as agent judgment (same class of judgment call as the parent skill's "already-resolved" button-label heuristic) rather than a hard percentage threshold, since title strings vary in how much punctuation/subtitle text differs between Covidence's citation and NotebookLM's recommendation card even for the same paper.
