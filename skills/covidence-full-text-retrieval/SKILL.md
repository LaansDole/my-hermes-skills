---
name: covidence-full-text-retrieval
description: Autonomously retrieve full-text PDFs for references in the full-text review stage of a Covidence systematic review, in the user's Chrome session via CDP. Looks up open-access copies via Unpaywall, Semantic Scholar, and arXiv, with an optional NotebookLM-assisted last-resort web search, then uploads any PDF it finds through Covidence's "Upload full text" action. References with no locatable full text get a note logged for manual follow-up. Never casts an Include/Exclude decision -- that stays manual.
version: 1.0.0
metadata:
  hermes:
    tags: [covidence, systematic-review, full-text, open-access, notebooklm, browser-automation]
    requires_toolsets: [browser, terminal]
---

# Covidence Full-Text Retrieval

## Parameters

- `max_refs` (int, default 100): hard cap on the number of references to process before stopping.
- `max_time` (int, default 60): hard cap on session wall-clock in minutes. Whichever of `max_refs` or `max_time` fires first stops the session.
- `daily_cap` (int, default 300): hard cap on total references processed across sessions in a single UTC day. `0` disables the daily cap. Persisted in `STATE.md`.
- `approve_first_n` (int, default 5): number of consequential actions (an upload or a not-found note) at the start of the session for which the agent pauses and waits for user confirmation before acting. After N approvals, the agent sets `auto_mode=true` and acts unattended for the rest of the session.
- `contact_email` (string, REQUIRED, no default): a real email address sent as the `email` query parameter on every Unpaywall API call, per Unpaywall's usage policy (https://unpaywall.org/products/api). If missing, or does not contain both `@` and `.`, REFUSE TO RUN and tell the user to supply it (e.g. `contact_email=you@example.org`).
- `download_dir` (string, default `~/.hermes/downloads/covidence-full-text-retrieval`): local scratch directory for PDFs fetched before upload. Created on first use if missing.
- `notebooklm_topic` (string, optional, no default): when set, enables Layer 4 of the Full-Text Discovery Step -- an AI-assisted last-resort web search via NotebookLM's "Discover sources" feature, run only for references Layers 1-3 (Unpaywall / Semantic Scholar / arXiv) could not resolve. Also names the single shared NotebookLM notebook used for this research topic (found by exact title match, or created if none exists). When omitted, Layer 4 is skipped entirely -- no NotebookLM tab is opened, and a Layer 1-3 miss goes straight to `NOT_FOUND`.
- `notebooklm_max_candidates` (int, default 3): only relevant when `notebooklm_topic` is set. How many of NotebookLM Discover's recommendation cards to evaluate per reference, best-ranked first, before declaring a Layer 4 miss for that reference.
- `dry_run` (bool, default false): when true, run full-text discovery for real (the lookups, including Layer 4's Discover search and source-add, are read-only-ish informational calls) but *describe* the upload or note action WITHOUT downloading past the validation check, clicking "Upload full text", calling `tab.uploadFile`, or opening the Covidence notes dialog. Use for first-pass validation against a real review or the Covidence Demo review.
- `tick_seconds` (int, default 5): idle polling interval between ticks when no action was taken. After an action, poll again immediately (the page needs time to react).

## Prerequisites

- A Chrome instance is running with `--remote-debugging-port=9222`.
- The user has logged into Covidence at `app.covidence.org` in that Chrome and is on the **Full text review -> Screen references** tab of the target review (NOT Resolve conflicts, Awaiting other reviewer, or Excluded references -- those are out of scope; see Safety Rules).
- Hermes's `terminal` toolset is enabled alongside `browser` (this skill shells out to `curl` and `python3` for open-access lookups -- see Full-Text Discovery Step). Verify with `hermes tools list`; both `browser` and `terminal` must show as enabled.
- `curl` and `python3` are on `$PATH` (macOS ships both by default).
- Hermes is attached to that Chrome via `/browser connect` (run this once per Hermes session before invoking the skill).
- Unlike `covidence-screening`, this skill does NOT require single-reviewer mode -- it never casts an Include/Exclude vote, so the reviewer-mode setting is irrelevant here.
- No PICO criteria file is needed -- this skill makes no inclusion/exclusion judgment. Full-text review decisions remain entirely manual.
- **If `notebooklm_topic` is set**: the user is already logged into `notebooklm.google.com` in the SAME Chrome instance (the one Hermes is attached to via CDP). No separate NotebookLM credential setup, no cookie export. If the NotebookLM tab redirects to a Google sign-in page when Layer 4 first tries to use it, the skill disables Layer 4 for the rest of the session (logs once, falls back to Layers 1-3 only) rather than blocking the whole run.
