# Claude Haiku 5.5 (max) vs GPT-6 Luna (max) in omp: why the small-model agents feel slower

- **Date:** 2026-10-14
- **Scope:** Is Haiku 5.5:max actually slower than GPT-6 Luna:max for omp's small-model agents (scout, reviewer, init), and which effort level should those agents use?
- **Method:** (1) Controlled probe: the same read-only code-review prompt (`watch_mentions.py`, top-3 bugs, tools `read,grep,glob`) run 2x each via `omp -p --mode json` on omp 18.10.0, for 4 configs (haiku-5-5 and gpt-6-luna at max and medium). (2) Historical omp session transcripts (`~/.omp/agent/sessions`, 2026-09-30 to 2026-10-14). (3) Artificial Analysis Haiku 5.5 (max) vs GPT-6 Luna (max) comparison page and Haiku 5.5 launch article, fetched 2026-10-14. Measured vs vendor-claimed values are labelled per row.

---

## Verdict

Yes, it is slower, and the cause is `:max` effort on Haiku, not the model itself: Haiku 5.5:max took 3.3x longer than Luna:max on the same review (456 s vs 139 s) because it wrote 10.6x more output tokens. Haiku 5.5:**medium** was the fastest of all four configs (31 s) and found an equally real top bug. Move `scout`, `reviewer` and `init` from `anthropic/claude-haiku-5-5:max` to `:medium` (or `:high` if review depth suffers), and keep `:max` only for one-off deep passes.

---

## Controlled probe (measured, n = 2 per config)

| Config | Wall time (s) | Mean wall (s) | Turns | Output tokens | Output tok/s | Cost (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku-5-5:medium | 35.1, 27.5 | 31 | 4, 4 | 5,119 / 3,754 | 141 | 0.0085 / 0.0049 |
| gpt-6-luna:medium | 81.9, 76.1 | 79 | 9, 9 | 5,698 / 4,808 | 66 | ~0 (gateway) |
| gpt-6-luna:max | 138.3, 140.2 | 139 | 18, 12 | 8,919 / 9,020 | 64 | ~0 (gateway) |
| haiku-5-5:max | 388.4, 523.7 | 456 | 6, 8 | 81,372 / 108,562 | 208 | 0.0636 / 0.0778 |

Output tok/s = output tokens / wall time (includes tool time, so it understates raw decode speed). Cost is omp's reported cost; Luna runs through the Command Code gateway, which reports ~0.

Ratios (computed): haiku:max / luna:max wall = 3.28x; haiku:max / haiku:medium wall = 14.6x; haiku:max / luna:max output tokens = 10.6x.

---

## Vendor benchmark (Artificial Analysis, vendor-measured, fetched 2026-10-14)

| Metric | Haiku 5.5 (max) | GPT-6 Luna (max) | Ratio |
| --- | ---: | ---: | ---: |
| Intelligence Index | 43 | 38 | +5 pts Haiku |
| Terminal-Bench 4.0 | 33% | 13% | Haiku |
| AutomationBench-AA | 35% | 53% | Luna |
| Output speed | 237 tok/s | 135 tok/s | 1.76x Haiku |
| Output tokens per task | 162k | 50k | 3.24x Haiku |
| Time to first answer token | 318.08 s | 88.98 s | 3.57x Haiku |
| End-to-end response time | 320.19 s | 92.68 s | 3.45x Haiku |
| Cost per task | $0.21 | $0.07 | 3.0x Haiku |
| Price per 1M in / out | $0.10 / $0.50 | $0.10 / $0.50 | same (Haiku 5x above 100k prompt tokens) |

---

## Findings

1. **"On paper stronger" is true but buys time, not speed.** Haiku 5.5 (max) leads the AA Intelligence Index 43 vs 38, but it spends ~3.2x the output tokens per task (AA) and 10.6x on this probe (measured). Its faster decode (237 vs 135 tok/s, AA) cannot cover that, so the end-to-end time is ~3.5x (AA) / 3.3x (measured) longer.
2. **`max` is the slow part.** AA: moving Haiku from xhigh to max adds 2 index points for ~1.8x the tokens. Measured: haiku:medium finished in 31 s vs 456 s at max, 14.6x faster, with 4 turns and ~4-5k output tokens.
3. **Your small-model agents run on Haiku:max today.** `omp config get task.agentModelOverrides` shows `scout`, `reviewer` and `init` pinned to `anthropic/claude-haiku-5-5:max`. (`modelRoles.smol` itself is still `commandcode/gpt-6-luna:medium`; the overrides bypass it.) In history (measured), Haiku 5.5:max sessions used a median 850 s of model time per session vs 115 s for Luna sessions, and a median 28.6 s per turn vs 8.0 s.
4. **Answer quality on this task was comparable; Haiku went deeper.** All 8 runs gave 3 plausible findings with file:line and fixes. Every Luna run and both Haiku:max runs flagged the same real defect (one 50-result search page per tick can drop mentions in a burst). Haiku:max also found issues Luna did not (a transient `auth.test` failure silently retargeting the watched user; bot-authored mentions dropped). Haiku:medium found the thread-pagination bug and the at-most-once state commit. ASSUMPTION: one task, n = 2, is not a quality benchmark; it only shows that medium did not collapse.
5. **Haiku's hidden cost cliff.** Above 100k prompt tokens Haiku 5.5 bills 5x ($0.50 / $2.50 per 1M, AA launch article). Historical Haiku sessions had a median 65k input tokens per turn, so long scout or review sessions can cross it.

---

## Recommendation

| Agent | Now | Proposed |
| --- | --- | --- |
| scout | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:medium |
| init | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:medium |
| reviewer (fast triage) | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:high (depth matters; escalation to reviewer-deep still covers P0/P1) |
| sonic | commandcode/gpt-6-luna:max | unchanged (Command Code currently being phased out by the user, so revisit) |

`task.agentModelOverrides` is a whole-record setting: write all 8 keys in one `omp config set task.agentModelOverrides '<json>'`, and back up `~/.omp/agent/config.yml` first.

---

## Caveats

- n = 2 per config on one read-only review task in one repo; latency varies with provider load (haiku:max ranged 388-524 s).
- Luna ran through the Command Code gateway and Haiku through Anthropic direct, so gateway overhead is mixed into the comparison. AA's numbers (same-provider style, 10k-token prompts) agree in direction and size.
- Historical session stats mix task types and are not like-for-like; they support, not prove, the probe.
- `reasoningTokens` is reported for Luna but 0 for Haiku in omp's usage records, so Haiku's thinking is counted inside `output`.

---

## References

- Artificial Analysis -- Claude Haiku 5.5 (Max) vs GPT-6 Luna (Max): <https://artificialanalysis.ai/models/comparisons/claude-haiku-5-5-vs-gpt-6-luna>
- Artificial Analysis -- Anthropic has released Claude Haiku 5.5 (Oct 7, 2026): <https://artificialanalysis.ai/articles/claude-haiku-5-5>
- Artificial Analysis -- GPT-6 Luna (Max) API provider benchmarking: <https://artificialanalysis.ai/models/gpt-6-luna/providers>
- Probe harness and raw results (local): `~/.hermes/cache/scratch/omp_bench.py`, `~/.hermes/cache/scratch/omp-bench/results.jsonl`
