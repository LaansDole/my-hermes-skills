# Covidence Full-Text Retrieval

Autonomously retrieve open-access full-text PDFs for references in the full-text review stage of a Covidence systematic review, and upload them via Covidence's "Link to full text" action. Looks up copies via Unpaywall, Semantic Scholar, arXiv, and an optional NotebookLM-assisted last-resort web search. References with no locatable full text are silently skipped (or noted for manual follow-up). Never casts an Include/Exclude decision — that stays manual.

**Version**: 1.2.0  
**Requires**: Hermes Agent v0.18+, browser + terminal toolsets, `curl` + `python3` on `$PATH`

## One-time setup

1. Install Hermes Agent v0.18+ (same install as `covidence-screening`; skip if already done).
2. Enable BOTH the `browser` and `terminal` toolsets:
   ```bash
   hermes tools list
   ```
   Expected: both `browser` and `terminal` show as enabled. If `terminal` is missing, run `hermes setup tools` and enable it (Terminal / Shell Access).
3. Confirm `curl` and `python3` are on `$PATH` (macOS ships both by default):
   ```bash
   curl --version | head -1
   python3 --version
   ```
4. Install the `websockets` Python package (used by the batch CDP script):
   ```bash
   pip3 install websockets
   ```
5. Merge the extra approval scopes into `~/.hermes/config.yaml` so the session runs unattended after onboarding, same pattern as `.hermes-config/config-patch.yaml`:
   ```yaml
   approvals:
     mode: scoped
     auto_approve:
       - browser.click
       - browser.type
       - browser.fill
       - browser.evaluate
       - browser.screenshot
       - browser.observe
       # terminal's exec/run action key varies by Hermes version --
       # run `hermes tools list --schema terminal` (or `hermes config show --defaults`)
       # to find the exact key in your installed version and add it here.
   ```
   Back up `~/.hermes/config.yaml` first (`cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d-%H%M%S)`). Without the terminal key added, every `curl` call this skill makes will pause for manual approval, defeating unattended operation after onboarding.
6. Symlink this skill into Hermes's skill directory (Hermes auto-discovers skills in `~/.hermes/skills/`; this repo is the source of truth):
   ```bash
   mkdir -p ~/.hermes/skills
   ln -sf "$(pwd)/skills/covidence-full-text-retrieval" ~/.hermes/skills/covidence-full-text-retrieval
   ```
   Verify:
   ```bash
   hermes skills list
   ```
   `covidence-full-text-retrieval` should appear.

7. Set up the `chrome-profiles` plugin to connect to your Brave browser profile (see the `cdp-browser-profiles` skill for details):
   ```bash
   # In ~/.hermes/plugins/chrome-profiles/config.yaml, add:
   profiles:
     brave-live:
       type: local
       browser_type: brave
       port: 9222
     research:
       type: local
       browser_type: brave
       port: 9254
       profile_directory: "Profile 3"   # your "Research" profile
   ```

## Per-review setup

1. Log into `app.covidence.org` in your browser (Brave recommended — set `browser_type: brave` in your profile config).
2. Open the target review and navigate to **Full text review -> Screen references**.
3. Have a real contact email ready to pass as `contact_email` — Unpaywall requires one on every lookup call.
4. No reviewer-mode change and no criteria file needed — this skill never casts an Include/Exclude vote.
5. **Optional — NotebookLM last-resort search (Layer 4)**: if you want the skill to try NotebookLM's "Discover sources" web search for references Unpaywall/Semantic Scholar/arXiv all miss, log into `notebooklm.google.com` in the SAME browser window (the one on port 9222). No cookie export, no separate credentials — the skill drives that tab directly. Skip this step entirely if you don't want Layer 4; the skill runs fine without it (just omit `notebooklm_topic` at launch).

## Launch a session

1. Start Brave (or Chrome) with remote debugging:
   ```bash
   open -na "Brave Browser" --args --remote-debugging-port=9222
   ```
2. In the browser, navigate to the review's **Full text review -> Screen references** tab. (If using Layer 4, also open a second tab logged into `notebooklm.google.com` — the skill will find and use it.)
3. Start Hermes:
   ```bash
   hermes -t browser,terminal chat
   ```
4. In the Hermes prompt:
   ```
   /browser connect
   ```
   Then, without Layer 4:
   ```
   run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, max_refs=100, max_time=60, dry_run=false
   ```
   Or, with the optional NotebookLM last-resort layer enabled:
   ```
   run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, notebooklm_topic="AI multi-agent depression screening review", max_refs=100, max_time=60, dry_run=false
   ```
   Adjust `max_refs`, `max_time`, `approve_first_n`, `daily_cap`, `download_dir`, `notebooklm_max_candidates`, `no_notes`, and `dry_run` as needed. For first-pass validation, use `dry_run=true` against the Covidence Demo review.

### Fully unattended mode

For a fully unattended run (no onboarding approvals, no manual notes for not-found refs):

```
run the covidence-full-text-retrieval skill on my current review, contact_email=you@example.org, approve_first_n=0, no_notes=true, max_refs=100, max_time=60
```

This is the recommended mode for production runs after you've validated the skill against your review.

## CDP WebSocket batch workflow (v1.2.0+)

When the Hermes browser tools have trouble attaching to the correct tab (common when multiple tabs are open), the skill falls back to a direct CDP WebSocket connection to the Covidence tab. This uses the `websockets` Python package (step 4 above) and a synchronous batch script that:

1. Connects directly to the Covidence tab's WebSocket endpoint (bypassing Hermes browser tools).
2. Clicks "Load more" to render all references (Covidence paginates at 100 refs per page).
3. Extracts ref metadata (ID, title, authors, DOI, arXiv ID) from the DOM.
4. Runs multi-layer discovery (Unpaywall → Semantic Scholar → arXiv → title-based arXiv search) for each unresolved ref.
5. Uploads found PDFs via the `uploadQueue` JS helper (link-to-full-text, not file upload).
6. Logs to JSONL and updates STATE.md.

Key CDP WebSocket pitfalls discovered in production:
- `ping_interval=None` is required — Brave's CDP endpoint drops WebSocket connections that send ping frames.
- `awaitPromise=False` must be used for void JS calls (e.g., `window.scrollTo()`) — Chrome never responds to `awaitPromise=True` for expressions that return `undefined`.
- The background reader thread pattern (Python 3.9 `asyncio.wait_for` + `CancelledError`) is buggy; use a synchronous `recv()` loop with a 0.2s timeout instead.

## First-run safety

Always do the first run as `dry_run=true` on the Covidence Demo review (or a test review), then a single-reference live run (`max_refs=1`), then an approve-first-N run (`max_refs=10, approve_first_n=5`) before going fully unattended. If using `notebooklm_topic`, do at least one dry run and one approved live run WITH it set before relying on Layer 4 unattended — confirm in the NotebookLM UI that only the intended notebook was touched.

## Quick reference

- **Parameters**: `max_refs` (100), `max_time` (60 min), `daily_cap` (300), `approve_first_n` (5), `no_notes` (false), `contact_email` (required), `notebooklm_topic` (optional), `notebooklm_max_candidates` (3), `dry_run` (false), `download_dir` (`~/.hermes/downloads/covidence-full-text-retrieval`), `tick_seconds` (5).
- **Discovery layers**: 1) Unpaywall (DOI) → 2) Semantic Scholar (DOI or title) → 3) arXiv direct (arXiv ID) → 3b) arXiv title search (for truncated/missing IDs) → 4) NotebookLM Discover (optional, title-based web search).
- **Known paywalled publishers** (never produce a PDF): IEEE (10.1109/\*), ACM (10.1145/\*), SPIE (10.1117/\*), SCITEPRESS (10.5220/\*), JCO/ASCO (10.1200/\*), Springer LNCS/CCIS (978-3-031-\*, 978-3-032-\* when not OA), Elsevier (10.1016/\* unless `is_oa: True`).
- **Upload mechanism**: Covidence's "Link to full text" (URL input in the Upload modal), NOT file upload — Hermes CDP has no `tab.uploadFile`. The `uploadQueue` JS helper in `scripts/upload_link.js` handles this in batch.
- **Stop conditions**: `max_refs` or `max_time` hit; daily cap (in `STATE.md`) hit; queue empty; approve-first-N `stop` response; CDP drop / login expired / 3 consecutive identical ref IDs; 3 consecutive references failing all discovery layers. A NotebookLM auth problem (Layer 4 only) disables Layer 4 for the rest of the session rather than stopping the run. Full detail in `SKILL.md` under "Loop Control".
- **Audit trail**: every tick appends a JSON line to `~/.hermes/logs/covidence-full-text-retrieval-<session-id>.jsonl`; not-found notes land in the per-reference notes field in Covidence (visible in the UI) or are silently skipped when `no_notes=true`; fetched PDFs are kept in `download_dir` (default `~/.hermes/downloads/covidence-full-text-retrieval`) for audit — clean this directory periodically, it is not auto-pruned; sources NotebookLM Discover adds (Layer 4 only) accumulate in the one notebook named by `notebooklm_topic`, including ones that didn't validate as a PDF — that notebook is a useful byproduct research artifact, not just a search cache; an end-of-session summary prints to the Hermes terminal. Full detail in `SKILL.md` under "Logging".
- **What this skill never does**: cast an Include/Exclude vote, touch `Move to screening`/`Duplicate`/bulk actions, fetch from paywall-circumvention sites, or (Layer 4 only) touch any NotebookLM notebook other than the one named by `notebooklm_topic`. Full-text review decisions stay 100% manual.