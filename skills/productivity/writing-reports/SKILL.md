---
name: writing-reports
description: "Use when the user asks for a report, research write-up, benchmark/model/tool comparison, or any 'give me the report' request."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [report, research, benchmark, comparison, references, documentation, filing]
    requires_toolsets: [terminal, web]
---

# Writing Reports

## Overview

A report is a decision document: **verdict first, evidence second, provenance always.** Every report ships in two parts: a dated markdown file (full) + a short chat lead (verdict + key table + file path).

## When to Use

- "give me a report" / research-then-writeup requests
- Benchmark, model, tool, price, or data comparisons

Not for: one-line answers, PR descriptions (pr skills), Covidence verdicts (own skill).

## Method

1. **Gather.** SearXNG search first (if :8888 down → restart-first rule, skill selfhosted-search). Scrape sources with curl + parse programmatically. Never single-source a number — cross-check prices/benchmarks in ≥2 independent sources (waived only in Trusted-Input Mode). Date-stamp: fetched data gets its fetch date, computed-only data gets the compute date.
2. **Compute.** All derived metrics (blends, ratios, per-point costs) calculated in Python, never mentally. State the formula next to the column (e.g. "blend = 3:1 in:out").
3. **Write the file.** `~/Projects/auto-learn-for-me/reports/YYYY-MM/YYYY-MM-DD-<slug>.md` (see Report Filing) — skeleton in `references/report-template.md`.
4. **Deliver.** Chat = verdict + the one key table + file path. If the user wants it in Word → pbcopy variant: plain text, ALL-CAPS headers, no markdown (skill pbcopy-word-delivery).

## Report Structure

`# Title` → metadata bullet list (Date / Scope / Method — one `- **Label:** value` bullet each) → Verdict (first sentence of prose) → tables → numbered findings → caveats → references. Fill the template; don't improvise structure.

## Hard Rules

- **Verdict in the first sentence of prose.** The metadata block comes first in the file (template order); the Verdict section opens with the decision — no "Executive summary" preamble, no restating the request.
- **Every number has a source or a formula.** Measured vs vendor-claimed vs derived — say which. Caller-supplied figures are labeled `caller-supplied` (not vendor-claimed).
- **Assumptions are labeled `ASSUMPTION:` inline** where used, never hidden in a footer.
- **References are numbered**: title — publisher — date — URL. Bare URLs are a defect. If a source is an unfetched URL with no known title, use `[unfetched — <url>]` as the title; never invent a plausible title.
- **No invented scenarios.** Illustrative math (e.g. monthly cost) must be flagged as an estimate with its basis.
- Chat lead follows ADHD shape: answer first, tables over prose, no preamble/recap (skill i-have-adhd).
- **Filing is the default.** Skip the file only when the caller explicitly forbids writing files; then say in the reply that the report is chat-only and unfiled.

## Trusted-Input Mode

When the caller supplies the data and forbids web search, the ≥2-source cross-check is waived — but the Method line must say `Inputs as supplied by caller, not independently verified`, and Caveats carries the single-source risk. Never silently skip verification.

## Report Filing (dated reports library)

Every report file lands in `~/Projects/auto-learn-for-me/reports/YYYY-MM/` as `YYYY-MM-DD-<slug>.md` (e.g. `2026-09-08-commandcode-cost-efficiency.md`) — this folder is the running library of past reports, so a later "that report we did on X" resolves to a file, not session memory.

- When a report is requested in chat, still write the file (chat is ephemeral; the file is the artifact).
- If a report was written elsewhere (a work repo, another machine path), move or symlink it into the library and note the original location in its metadata block.
- Need something from an old report? `ls reports/YYYY-MM/` or search by slug before re-researching.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| "Executive summary" heading before the verdict | Verdict IS the first line |
| Bare URL in references | Numbered: title — publisher — date — URL |
| Metric column with no formula | Formula beside the column header or footnote |
| Unlabeled invented usage scenario | `ASSUMPTION:` inline + basis |
| Full report dumped into chat | File + short lead; chat table ≤ 10 rows |
| Report only in chat, no file | Chat is ephemeral — file it: `reports/YYYY-MM/YYYY-MM-DD-<slug>.md` |
