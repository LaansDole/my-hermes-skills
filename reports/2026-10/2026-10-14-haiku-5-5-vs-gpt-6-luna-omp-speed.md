# Why do omp's small-model agents feel slower on Claude Haiku 5.5 (max) than on GPT-6 Luna (max)?

- **Date:** 2026-10-14
- **Report type:** Technical investigation
- **Keywords:** Claude Haiku 5.5, GPT-6 Luna, omp subagents, reasoning effort, latency, output tokens
- **Data collected:** probe runs 2026-10-14 (omp 18.10.0); omp session transcripts 2026-09-30 to 2026-10-14; Artificial Analysis pages fetched 2026-10-14.

## Abstract

**Background.** omp's small-model agents (`scout`, `reviewer`, `init`) felt slow after being pinned to Claude Haiku 5.5 at `:max` effort, although Haiku 5.5 is stronger on paper than GPT-6 Luna.
**Objective.** To determine whether Haiku 5.5:max is actually slower than GPT-6 Luna:max for these agents, why, and which effort level they should use.
**Methods.** A controlled probe ran the same read-only code-review prompt twice for each of four configurations (both models at max and medium) via `omp -p --mode json` [1]. Historical omp session transcripts were summarised, and Artificial Analysis (AA) comparison, launch and provider pages were consulted [2, 3, 4].
**Results.** Haiku 5.5:max took 456 s versus 139 s for Luna:max on the same review (3.3x, measured) [1], writing 10.6x more output tokens. Haiku 5.5:medium was the fastest configuration at 31 s. AA reports Haiku's end-to-end response time as 3.45x Luna's despite 1.76x faster output speed, because it uses 3.24x the output tokens per task [2, 3]. Historical Haiku:max sessions used a median 850 s of model time versus 115 s for Luna (measured).
**Conclusions.** Yes, Haiku 5.5:max is slower, and the cause is `:max` effort on Haiku, not the model itself. Move `scout`, `reviewer` and `init` from `anthropic/claude-haiku-5-5:max` to `:medium` (or `:high` if review depth suffers), and keep `:max` only for one-off deep passes.

## 1. Introduction

omp lets each subagent be pinned to a model and effort level through `task.agentModelOverrides`. `omp config get task.agentModelOverrides` showed `scout`, `reviewer` and `init` pinned to `anthropic/claude-haiku-5-5:max`, while `modelRoles.smol` itself was still `commandcode/gpt-6-luna:medium`; the overrides bypass it. Haiku 5.5 (max) leads GPT-6 Luna (max) on the AA Intelligence Index [3], yet the agents felt slower.

- **RQ1.** Is Haiku 5.5:max slower than GPT-6 Luna:max for omp's small-model agents, and by how much?
- **RQ2.** What causes the difference?
- **RQ3.** Which effort level should those agents use?

## 2. Methods

### 2.1 Sources and search strategy

Three sources: (1) a controlled local probe [1]; (2) historical omp session transcripts in `~/.omp/agent/sessions`, 2026-09-30 to 2026-10-14; (3) the AA Haiku 5.5 (max) vs GPT-6 Luna (max) comparison page [2] and Haiku 5.5 launch article [3], fetched 2026-10-14. The AA GPT-6 Luna provider benchmarking page [4] was also consulted; no figure in this report is taken from it.

### 2.2 Evidence classification

- **Measured:** the probe (Table 1) and the historical session statistics.
- **Third-party benchmark:** AA figures (Table 2) [2, 3]. AA is an independent benchmarker, not the model vendor.
- **Derived:** ratios and output tokens per second.

### 2.3 Experimental setup

The same read-only code-review prompt (`watch_mentions.py`, top-3 bugs, tools `read,grep,glob`) was run 2x each via `omp -p --mode json` on omp 18.10.0, for 4 configs: haiku-5-5 and gpt-6-luna at max and medium [1]. Luna ran through the Command Code gateway and Haiku through Anthropic direct. Hardware and whether runs were concurrent were not recorded.

### 2.4 Analysis

- Output tok/s = output tokens / wall time (includes tool time, so it understates raw decode speed).
- Ratios: haiku:max / luna:max wall time; haiku:max / haiku:medium wall time; haiku:max / luna:max output tokens.
- Cost is omp's reported cost; the Command Code gateway reports ~0 for Luna.
- Historical statistics are medians over sessions and turns by model.

## 3. Results

### 3.1 Controlled probe (RQ1)

Table 1. Controlled probe, n = 2 per config (measured) [1].

| Config | Wall time (s) | Mean wall (s) | Turns | Output tokens | Output tok/s | Cost (USD) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| haiku-5-5:medium | 35.1, 27.5 | 31 | 4, 4 | 5,119 / 3,754 | 141 | 0.0085 / 0.0049 |
| gpt-6-luna:medium | 81.9, 76.1 | 79 | 9, 9 | 5,698 / 4,808 | 66 | ~0 (gateway) |
| gpt-6-luna:max | 138.3, 140.2 | 139 | 18, 12 | 8,919 / 9,020 | 64 | ~0 (gateway) |
| haiku-5-5:max | 388.4, 523.7 | 456 | 6, 8 | 81,372 / 108,562 | 208 | 0.0636 / 0.0778 |

Ratios (derived): haiku:max / luna:max wall = 3.28x; haiku:max / haiku:medium wall = 14.6x; haiku:max / luna:max output tokens = 10.6x.

All 8 runs gave 3 plausible findings with file:line and fixes. Every Luna run and both Haiku:max runs flagged the same real defect (one 50-result search page per tick can drop mentions in a burst). Haiku:max also found issues Luna did not (a transient `auth.test` failure silently retargeting the watched user; bot-authored mentions dropped). Haiku:medium found the thread-pagination bug and the at-most-once state commit.

### 3.2 Third-party benchmark (RQ2)

Table 2. Artificial Analysis comparison, fetched 2026-10-14 (third-party benchmark).

| Metric | Haiku 5.5 (max) | GPT-6 Luna (max) | Ratio |
| --- | ---: | ---: | ---: |
| Intelligence Index [2, 3] | 43 | 38 | +5 pts Haiku |
| Terminal-Bench 4.0 [3] | 33% | 13% | Haiku |
| AutomationBench-AA [3] | 35% | 53% | Luna |
| Output speed [2] | 237 tok/s | 135 tok/s | 1.76x Haiku |
| Output tokens per task [3] | 162k | 50k | 3.24x Haiku |
| Time to first answer token [2] | 318.08 s | 88.98 s | 3.57x Haiku |
| End-to-end response time [2] | 320.19 s | 92.68 s | 3.45x Haiku |
| Cost per task [2] | $0.21 | $0.07 | 3.0x Haiku |
| Price per 1M in / out [3] | $0.10 / $0.50 | $0.10 / $0.50 | same (Haiku 5x above 100k prompt tokens) |

AA reports that moving Haiku from xhigh to max adds 2 index points for ~1.8x the tokens [3]. Above 100k prompt tokens Haiku 5.5 bills 5x ($0.50 / $2.50 per 1M) [3].

### 3.3 Historical sessions

In omp history (measured), Haiku 5.5:max sessions used a median 850 s of model time per session vs 115 s for Luna sessions, and a median 28.6 s per turn vs 8.0 s. Historical Haiku sessions had a median 65k input tokens per turn.

## 4. Discussion

### 4.1 Principal findings

RQ1: yes, Haiku 5.5:max is slower, 3.3x on the probe (456 s vs 139 s) [1]. RQ2: "on paper stronger" is true but buys time, not speed. Haiku 5.5 (max) leads the AA Intelligence Index 43 vs 38 [3], but it spends ~3.2x the output tokens per task (AA) [3] and 10.6x on this probe (measured) [1]. Its faster decode (237 vs 135 tok/s, AA) [2] cannot cover that, so the end-to-end time is ~3.5x (AA) [2] / 3.3x (measured) [1] longer. `max` is the slow part: Haiku:medium finished in 31 s vs 456 s at max, 14.6x faster, with 4 turns and ~4-5k output tokens [1]. On this one task, answer quality was comparable and Haiku went deeper; medium did not collapse.

### 4.2 Comparison with prior work

The probe and AA agree in direction and size, although AA uses a same-provider style setup with 10k-token prompts [2]. The historical session medians point the same way. A hidden cost cliff also applies: with a median 65k input tokens per turn, long scout or review sessions can cross Haiku's 100k-token 5x price threshold [3].

### 4.3 Practical implications

RQ3: Table 3 lists the proposed overrides. `task.agentModelOverrides` is a whole-record setting: write all 8 keys in one `omp config set task.agentModelOverrides '<json>'`, and back up `~/.omp/agent/config.yml` first.

Table 3. Proposed subagent settings.

| Agent | Now | Proposed |
| --- | --- | --- |
| scout | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:medium |
| init | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:medium |
| reviewer (fast triage) | anthropic/claude-haiku-5-5:max | anthropic/claude-haiku-5-5:high (depth matters; escalation to reviewer-deep still covers P0/P1) |
| sonic | commandcode/gpt-6-luna:max | unchanged (Command Code currently being phased out by the user, so revisit) |

## 5. Limitations

- **Sample size.** n = 2 per config on one read-only review task in one repo; latency varies with provider load (haiku:max ranged 388-524 s). One task with n = 2 is not a quality benchmark; it only shows that medium did not collapse.
- **Access paths.** Luna ran through the Command Code gateway and Haiku through Anthropic direct, so gateway overhead is mixed into the comparison.
- **Historical data.** Session stats mix task types and are not like-for-like; they support, not prove, the probe.
- **Token accounting.** `reasoningTokens` is reported for Luna but 0 for Haiku in omp's usage records, so Haiku's thinking is counted inside `output`.
- **Staleness.** AA figures have since been updated [2].
- **Cost basis.** Luna's ~0 cost is a gateway artefact, not a per-token price.

## 6. Conclusion

Haiku 5.5:max makes omp's small-model agents slow because max effort multiplies output tokens far beyond what Haiku's faster decoding can offset; at medium effort Haiku was the fastest configuration tested. The agents should run Haiku at medium (high for the reviewer), with max reserved for occasional deep passes.

## Data and code availability

Probe harness and raw results (local): `~/.hermes/cache/scratch/omp_bench.py`, `~/.hermes/cache/scratch/omp-bench/results.jsonl` [1].

## References

[1] Probe harness and raw results (local): `~/.hermes/cache/scratch/omp_bench.py`, `~/.hermes/cache/scratch/omp-bench/results.jsonl`
[2] Artificial Analysis, Claude Haiku 5.5 (Max) vs GPT-6 Luna (Max) comparison (fetched 2026-10-14; figures since updated): <https://artificialanalysis.ai/models/comparisons/claude-haiku-5-5-vs-gpt-6-luna>
[3] Artificial Analysis, Anthropic has released Claude Haiku 5.5 (Oct 7, 2026): <https://artificialanalysis.ai/articles/claude-haiku-5-5>
[4] Artificial Analysis, GPT-6 Luna (Max) API provider benchmarking: <https://artificialanalysis.ai/models/gpt-6-luna/providers>
