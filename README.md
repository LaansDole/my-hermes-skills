# hermes-covidence-screening

A [Hermes Agent](https://hermes-agent.nousresearch.com/) skill that autonomously screens references at the **title & abstract** stage of a [Covidence](https://www.covidence.org/) systematic review in your own Chrome session via the Chrome DevTools Protocol (CDP).

The agent votes **Yes / Maybe / No** per reference against your PICO criteria (defined in `CRITERIA.md`), writes a one-line rationale for **Maybe** votes into the per-reference notes dialog, and runs unattended after an **approve-first-N** onboarding phase.

Built on Hermes Agent (Nous Research, MIT). The agent attaches to your already-logged-in Chrome via CDP, so no Covidence SSO/2FA automation or credentials-in-the-agent is needed.

## How it works

```
[Your Chrome, logged into Covidence (app.covidence.org)]
       |  CDP via --remote-debugging-port=9222
       |  Hermes attaches with /browser connect
       v
[Hermes Agent]  <-- skills/covidence-screening/SKILL.md
       |         <-- skills/covidence-screening/CRITERIA.md  (PICO + inclusion/exclusion)
       |         <-- skills/covidence-screening/STATE.md    (daily-cap counter)
       |
       |  vision-capable model (via Nous Portal)
       v
[Screen loop: observe -> read reference -> classify vs criteria -> vote -> next block]
```

Each tick: observe the accessibility tree + URL, classify the page state (`REVIEW_SUMMARY` / `TA_SCREENING` / `UNKNOWN`), walk the T&A list top-to-bottom, run the decision step on the first unvoted reference, cast the vote (with notes for Maybe), and continue. A vision pass is used only as a fallback when the a11y tree is ambiguous (icon-only buttons, shadow-DOM notes dialog).

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `max_refs` | int | 200 | Hard cap on references to vote on before stopping. |
| `max_time` | int | 90 | Hard cap on session wall-clock in minutes. Whichever of `max_refs` / `max_time` fires first stops the session. |
| `daily_cap` | int | 500 | Hard cap on total references voted across sessions in a single UTC day. `0` disables. Persisted in `STATE.md`. |
| `approve_first_n` | int | 5 | Number of votes at the start of the session for which the agent pauses and waits for user confirmation. After N approvals, the agent flips to unattended mode. |
| `dry_run` | bool | false | When true, observe and describe the vote you would cast (with Maybe rationale) WITHOUT clicking. |
| `tick_seconds` | int | 5 | Idle polling interval. After an action, poll again immediately. |

## Prerequisites

- **macOS** (tested target; Linux/Windows should work since Hermes is cross-platform, but the Chrome launch command in this README is macOS-specific)
- [Hermes Agent](https://hermes-agent.nousresearch.com/) v0.18+
- A [Nous Portal](https://portal.nousresearch.com) subscription (gives the agent a vision-capable model via the Tool Gateway)
- Google Chrome (Chromium-family; Brave/Edge also work)
- A Covidence account with a systematic review assigned to you

## One-time setup

### 1. Install Hermes Agent

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

Open a new shell so `hermes` is on `$PATH`. Verify:

```bash
hermes --version   # must be >= 0.18.0
```

### 2. Install the skill

```bash
hermes skills install LaansDole/hermes-covidence-screening
```

This copies the skill to `~/.hermes/skills/covidence-screening/`. Verify:

```bash
hermes skills list | grep covidence
```

### 3. Log in to Nous Portal

```bash
hermes setup --portal
```

### 4. Enable the browser toolset in local CDP mode

```bash
hermes setup tools
```

In the interactive menu, select **Browser Automation** -> **Local Chromium-family CDP**. Do NOT pick Browserbase / Browser Use / Firecrawl / Camofox -- those are cloud providers and out of scope for this project.

Verify:

```bash
hermes tools list
```

`browser` should appear in the enabled toolsets column.

### 5. Edit `CRITERIA.md`

Fill in your PICO + inclusion/exclusion bullets:

```bash
$EDITOR ~/.hermes/skills/covidence-screening/CRITERIA.md
```

If it still contains the template placeholder text, the skill will refuse to run.

### 6. Set the review to single-reviewer mode

In Covidence: **Settings** -> **Switch to single reviewer**. In dual mode the agent's vote alone will not advance references; do not run in dual mode.

## Per-session launch

### 1. Start Chrome with remote debugging

Quit Chrome fully first (Cmd-Q) -- the flag only takes effect on a fresh launch:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/Library/Application Support/Google/Chrome" &
```

Verify the debug port is listening:

```bash
curl -s http://127.0.0.1:9222/json/version | head -1
```

### 2. Log in and open the review

In Chrome: navigate to `app.covidence.org`, log in via institutional SSO/2FA, open the target review, and click into the **Title and Abstract Screening** page (the scrollable list of references, not the Review Summary dashboard).

### 3. Start Hermes and attach

```bash
hermes -t browser chat
```

In the Hermes prompt:

```
/browser connect
```

### 4. Invoke the skill

```
run the covidence-screening skill on my current review, max_refs=200, max_time=90, dry_run=false
```

Per-tick logs land at `~/.hermes/logs/covidence-screening-<session-id>.jsonl`. A summary (refs screened, Yes/Maybe/No counts, Maybe rationales, stuck points, daily-cap remaining) prints at the end.

## First-run safety pattern

Before the first unattended run, do these validation passes:

1. **Dry run** on the Demo review: `max_refs=10, dry_run=true`. Watch the described decisions; tune `CRITERIA.md` if the reasoning misfires.
2. **Single-ref live run**: `max_refs=1`. Confirm one vote lands and the block updates.
3. **Approve-first-N live run**: `max_refs=10, approve_first_n=5`. Confirm the onboarding loop pauses for confirmation, then flips to unattended after 5 approvals.

If clean, do the full unattended run.

## Safety guardrails (built into the skill)

- Never types into password fields (Hermes hard-blocks this anyway).
- Never clicks elements named logout / sign out / sign-out / signout / log off.
- Strict allowlist of T&A screening list + Review Summary page; never clicks into Full Text, Data Extraction, Risk of Bias, or Settings.
- Never clicks the top-toolbar buttons (`Sort`, `Filter`, `Show criteria`, `More options`).
- Stops the loop if the page navigates outside the `covidence.org` domain.
- Read-only on everything except vote buttons and the per-reference notes dialog; never modifies review criteria, team members, or settings.
- Bounded session via `max_refs` / `max_time` / `daily_cap`.
- Idempotency guards: never votes twice on the same `Ref ID`; infinite-loop guard stops if the last 3 `Ref ID`s are identical after actions.
- Re-vote guard: never re-opens an already-voted reference.
- Hermes's built-in destructive-action blocklists (recursive force-delete, piped-shell installers, fork bombs, lock-screen combos) remain active and are NOT overridden by this skill.

## Explicit non-goals

- Covidence institutional SSO login automation -- you stay logged in via your real Chrome.
- Full-text screening, data extraction, risk-of-bias assessment.
- Dual-reviewer mode (the review must be set to single-screener before running).
- External lookups (PubMed, DOI, publisher PDFs) -- Covidence metadata only.
- Anti-detection / stealth -- if Covidence detects automation, that's a policy problem for you, not a design problem.
- Multi-review parallelism -- one review at a time.

## Repository layout

```
.
`-- skills/
    `-- covidence-screening/
        |-- SKILL.md        # screen-loop instructions, state machine, action policy, safety rules
        |-- CRITERIA.md     # PICO + inclusion/exclusion template (user fills in)
        |-- STATE.md        # daily-cap counter (auto-created/updated at runtime)
        `-- SETUP.md        # per-session launch steps
```

## License

This skill is MIT-licensed. Hermes Agent itself is MIT-licensed by Nous Research.

Covidence is a registered trademark of its respective owner; this project is not affiliated with or endorsed by Covidence.
