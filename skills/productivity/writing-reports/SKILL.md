---
name: writing-reports
description: "Use when the user asks for a report, research write-up, benchmark/model/tool comparison, or any 'give me the report' request."
version: 2.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [report, research, benchmark, comparison, references, documentation, filing, imrad]
    requires_toolsets: [terminal, web]
---

# Writing Reports

## Overview

Reports are written as short research papers: a structured abstract, then Introduction, Methods, Results, Discussion (IMRaD), Limitations, Conclusion and numbered references. A reader should be able to judge how strong each claim is from the report alone: where the evidence came from, how it was measured, and what it can't show. Every report ships in two parts: a dated markdown file (full) and a short chat lead (conclusion + key table + file path).

The structure follows standard IMRaD practice for empirical write-ups. Prose guidance is borrowed from the academic-research-skills plugin (`academic-paper/references/writing_quality_check.md` under `~/.omp/plugins/node_modules/academic-research-skills/`); read it before drafting long reports.

## When to Use

- "give me a report" / research-then-writeup requests
- Benchmark, model, tool, price, or data comparisons
- Technical investigations (root-causing a bug, evaluating an integration)

Not for: one-line answers, PR descriptions (pr skills), Covidence verdicts (own skill), journal manuscripts (research-paper-writing / scoping-review-writing).

## Method

1. **Gather.** Search and fetch through Camofox (`web_search` / `web_extract`; skill camofox-browser). Never single-source a number: cross-check prices/benchmarks in at least 2 independent sources (waived only in Trusted-Input Mode). Record the fetch date of every source and the run date of every measurement.
2. **Compute.** All derived metrics (blends, ratios, per-point costs, significance tests) are calculated in Python, never mentally. The formula goes in Methods 2.4 and beside the derived column.
3. **Write the file.** `~/Projects/auto-learn-for-me/reports/YYYY-MM/YYYY-MM-DD-<slug>.md` (see Report Filing), filling `references/report-template.md`.
4. **Deliver.** Chat = the Conclusions sentence + the one key table + file path. If the user wants it in Word: plain text, ALL-CAPS headers, no markdown, piped to `pbcopy`.

## Report Structure

`# Title` → metadata bullets (Date / Report type / Keywords / Data collected) → `## Abstract` (five bold-labelled paragraphs: Background, Objective, Methods, Results, Conclusions) → `## 1. Introduction` (ends with RQ1..n) → `## 2. Methods` → `## 3. Results` → `## 4. Discussion` → `## 5. Limitations` → `## 6. Conclusion` → optional `## Data and code availability` → `## References`. Number top-level sections; subsections as `### 2.1`. Number and caption tables (`Table 1. ...`) above the table.

Report types adjust the middle, not the frame:

| Type | Methods emphasis | Results shape |
| --- | --- | --- |
| Benchmark study | Setup, runs, harness, statistics | Tables of measured numbers |
| Evidence review | Search strategy, source types, inclusion | Synthesis by RQ, evidence-type labels |
| Technical investigation | Environment, reproduction, measurements | Observations in order of diagnosis |
| Technical guide | System context, versions, validation done | Procedure moves to an Appendix; Results = what was verified |

## Hard Rules

- **The Abstract's Conclusions paragraph opens with the answer.** It is the decision a reader would otherwise scroll for, and the docs site uses its first sentence as the report summary. No "Executive summary" heading, no restating the request.
- **Results report; Discussion interprets.** Keep recommendations out of Results and new evidence out of Discussion and Conclusion.
- **Every number has a source or a formula, and an evidence type.** Measured (own run), third-party benchmark, vendor-reported, community report, or derived. Caller-supplied figures are labeled `caller-supplied`. Community posts are leads, not findings.
- **Hedge to the evidence.** "shows" only for measured or replicated results; "suggests" / "reported" for single sources and community posts. No intensifiers (crucial, robust, comprehensive) without a number behind them.
- **Assumptions are labeled `ASSUMPTION:` inline** where used, never hidden in a footer.
- **Cite inline, number the references.** Every sourced claim, number or quote carries an inline marker right after it: `[n]`, or `[n, m]` for several sources. `## References` lists each source once, numbered in order of first citation: `[n] Title: <URL>` (publisher and date when useful, URL in angle brackets). No bare URLs; for unfetched URLs use `[n] [unfetched — <URL>]`. The docs site turns markers into linked superscripts with hover previews and back-links. The set of cited numbers must equal the set of reference numbers before filing.
- **Limitations are a real section.** Sample size, ceiling effects, staleness, single-source numbers, access failures (403s, paywalls) and harness bias all go there.
- **No `---` separators between sections.** Headings separate sections.
- **No invented scenarios.** Illustrative math (e.g. monthly cost) is flagged as an estimate with its basis.
- **Chat lead follows ADHD shape:** answer first, tables over prose, no preamble/recap (skill i-have-adhd).
- **Filing is the default.** Skip the file only when the caller explicitly forbids writing files; then say the report is chat-only and unfiled.

## Trusted-Input Mode

When the caller supplies the data and forbids web search, the 2-source cross-check is waived, but the `Data collected` bullet and Methods 2.1 must say `Inputs as supplied by caller, not independently verified`, and Limitations carries the single-source risk. Never silently skip verification.

## Rewriting an older report into this format

Restructure only. Keep every number, citation, caveat and reference; do not add facts, re-fetch sources, or change a conclusion. Move the old Verdict into the Abstract's Conclusions, old Findings into Results (observations) and Discussion (interpretation), old Caveats into Limitations. Afterwards, check that the multiset of numbers and the set of reference URLs are unchanged.

## Report Filing (dated reports library)

Every report file lands in `~/Projects/auto-learn-for-me/reports/YYYY-MM/` as `YYYY-MM-DD-<slug>.md` (e.g. `2026-09-08-commandcode-cost-efficiency.md`). This folder is the running library of past reports, so a later "that report we did on X" resolves to a file, not session memory. The docs site and the `reports` array in `skills.json` are generated from it.

- When a report is requested in chat, still write the file (chat is ephemeral; the file is the artifact).
- If a report was written elsewhere, move or symlink it into the library and note the original location in its metadata block.
- Need something from an old report? `ls reports/YYYY-MM/` or search by slug before re-researching.

## Common Mistakes

| Mistake | Fix |
| --- | --- |
| "Executive summary" or "Verdict" heading | Structured Abstract; answer opens Conclusions |
| Recommendation inside Results | Move to 4.3 Practical implications |
| Reddit snippet reported as a finding | Label as community report; discuss, don't conclude from it |
| Bare URL in references | Numbered `[n] Title: <URL>` per source |
| Sources listed but never cited | Inline `[n]` after each sourced claim; cited set = reference set |
| Derived column with no formula | Formula in 2.4 and beside the column |
| Caveats as a throwaway list | `## 5. Limitations` naming the threat and its effect on the result |
| Unlabeled invented usage scenario | `ASSUMPTION:` inline + basis |
| Full report dumped into chat | File + short lead; chat table at most 10 rows |
| Report only in chat, no file | File it: `reports/YYYY-MM/YYYY-MM-DD-<slug>.md` |
