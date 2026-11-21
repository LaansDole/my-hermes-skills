# Is GLM-5.3-Flash the most cost-efficient model on the CommandCode catalog?

- **Date:** 2026-09-08
- **Report type:** Evidence review
- **Keywords:** CommandCode, GLM-5.3-Flash, cost per intelligence point, Artificial Analysis, model pricing
- **Data collected:** Artificial Analysis model pages, OpenRouter pricing pages, Ampere.sh and vendor docs fetched on or before 2026-09-08 (exact fetch time not recorded); catalog state as of 2026-09-08.

## Abstract

**Background.** GLM-5.3-Flash is the daily-driver model in Hermes and the `@smol` role model in omp, both served through the CommandCode Provider API, so a cheaper or better model on the same catalog would change a default used every day.
**Objective.** To determine whether any model on the CommandCode catalog offers better performance per unit cost than GLM-5.3-Flash, and what the alternatives are if more capability or speed is needed.
**Methods.** Artificial Analysis (AA) model pages were found through a self-hosted SearXNG search, scraped with curl and parsed programmatically for Intelligence Index scores, list prices and throughput. Prices were cross-checked against OpenRouter [1, 2]; a third-party flagship-versus-Flash comparison [3] and vendor documentation [4, 5] supplied coding benchmarks and model facts. Efficiency was ranked by AA's full-suite evaluation cost per Index point.
**Results.** GLM-5.3-Flash scores 42 on the Intelligence Index at $0.15/$0.50 per 1M tokens, giving a suite cost of $6.7 per Index point, the lowest of 8 ranked models [6]. The other ranked models cost from $13.5 (DeepSeek V4 Flash) to $135.8 (GPT-5.5) per point, with the flagship GLM-5.3 at $55.6 [7, 8, 9, 10, 11, 12, 13]. On coding benchmarks Flash trails the flagship by 3.5 to 3.9 points on Terminal Bench and DeepSWE and leads on AutomationBench (48.8 vs 48.2) [3].
**Conclusions.** Keep GLM-5.3-Flash as the daily driver: it is the most cost-efficient model on the CommandCode catalog by a wide margin (about 8x cheaper per Index point than GLM-5.3), and no switch is recommended. GLM-5.3 is the only sensible upgrade for more capability, and DeepSeek V4 Flash the option for throughput-bound batch work.

## 1. Introduction

GLM-5.3-Flash runs as the default model in two places: Hermes (`z-ai/glm-5.3-flash` via the `commandcode` provider) and omp's `@smol` role. CommandCode exposes a rotating catalog of models from several vendors, and the question is whether the current default is still the best value on it. This review compares the catalog using AA's Intelligence Index and price data [6, 7, 8, 9, 10, 11, 12, 13, 14], with a third-party flagship comparison [3, 15] for the coding gap.

- **RQ1.** Which model on the CommandCode catalog has the lowest cost per unit of measured intelligence?
- **RQ2.** How large is the coding-quality gap between GLM-5.3-Flash and its flagship GLM-5.3, relative to the price gap?
- **RQ3.** Which model should be used if more capability or more throughput is needed?

## 2. Methods

### 2.1 Sources and search strategy

Sources were located through a self-hosted SearXNG instance. AA model pages (Intelligence Index v4.3, list prices, throughput) were scraped via curl and parsed programmatically. OpenRouter pricing pages for GLM 5.3 [1] and Kimi K3 [2] served as a price cross-check. The Ampere.sh GLM-5.3-versus-Flash comparison (Aug 27, 2026) supplied coding benchmarks [3], and a second Ampere.sh article (GLM 5.3 Flash vs GPT-5.4 Mini) the context-window figure [15]. Z.ai developer docs [4] and the Hugging Face model card [5] supplied architecture and modality facts. Search terms and exclusion criteria were not recorded. The models compared are those on the CommandCode catalog as of 2026-09-08.

### 2.2 Evidence classification

- **Third-party benchmark:** AA Intelligence Index, throughput, tokens generated on the AA suite; Ampere.sh benchmark table [3].
- **Third-party price tracking:** AA-tracked first-party list prices per 1M tokens (Sep 2026), cross-checked with OpenRouter [1, 2].
- **Vendor-reported:** parameter counts, modality and context window [4, 5].
- **Derived:** blended price, ratios between models.
- **Observed configuration:** the local Hermes and omp settings in Table 3, recorded as verified working on 2026-09-08.

### 2.3 Experimental setup

No models were run. The scrape output and computed ratios were kept in session scratch files (see Data and code availability).

### 2.4 Analysis

- **Blend $/1M** = (3 x input price + 1 x output price) / 4, a 3:1 input:output token mix used as a standard workload approximation.
- **Suite cost per II point** = AA's full Intelligence Index evaluation suite cost divided by the model's Index score, as published by AA (their apples-to-apples efficiency measure).
- **Ratios** in the text (for example 55.6 / 6.7 = 8.3, rounded to "roughly 8x") were computed from Table 1.

## 3. Results

### 3.1 Cost per intelligence point across the catalog

Table 1. CommandCode catalog sorted by AA suite cost per Intelligence Index point (third-party benchmark and price tracking; Blend is derived). Prices are list prices per 1M tokens as tracked by AA (first-party serving, Sep 2026). II is the AA Intelligence Index v3.4.3-class score as published on each model page (higher is better; page-stated medians ranged 17–24 at fetch time). Blend = 3:1 input:output token mix.

| Model | II | In $/1M | Out $/1M | Blend $/1M | Suite cost per II pt (USD) | tok/s | Params (total / active) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **GLM-5.3-Flash** [6] | **42** | **0.15** | **0.50** | **0.24** | **6.7** | 60 | 320B / 18B |
| DeepSeek V4 Flash [7] | 35 | 0.44 | 1.32 | 0.66 | 13.5 | 126 | 284B / 13B |
| DeepSeek V4 Pro [8] | 36 | 1.32 | 3.96 | 1.98 | 31.2 | 77 | 1.6T / 49B |
| GLM-5.3 [9] | 45 | 1.40 | 4.40 | 2.15 | 55.6 | 71 | 753B / 40B |
| Gemini 3.5 Flash [10] | 33 | 1.50 | 9.00 | 3.38 | 65.8 | 216 | n/a |
| Qwen3.8 Max [11] | 40 | 2.00 | 6.00 | 3.00 | 79.3 | 40 | n/a |
| Kimi K3 [12] | 44 | 3.00 | 15.00 | 6.00 | 83.1 | 42 | 2.8T / 104B |
| GPT-5.5 [13] | 39 | 5.00 | 30.00 | 11.25 | 135.8 | 90 | n/a |
| GLM-5.2 [14] | 39 | 1.40 | 4.40 | 2.15 | n/a | 62 | n/a |

GLM-5.3-Flash has the lowest suite cost per Index point, $6.7, against $55.6 for GLM-5.3 (derived ratio roughly 8x) and $135.8 for GPT-5.5 (~20x) [6, 9, 13]. GLM-5.2 has no published suite cost [14].

Token consumption on the AA suite: GLM-5.3-Flash generated 180M tokens (verbose, rank 25/112) [6], GLM-5.3 210M [9] and DeepSeek V4 Flash 240M [7].

### 3.2 GLM-5.3-Flash profile

- Intelligence Index 42, above the class median of ~17 (third-party benchmark) [6]; 1M context window [6, 15]; 60 tok/s output [6].
- Natively multimodal (vision), the only vision-capable GLM-5.3 variant (vendor-reported) [4, 5]; the standard GLM-5.3 is primarily text-based [3]. Vendor docs list input modality as Video / Image / Text / File [4].
- Sparse architecture: 320B total parameters with 18B active per token (vendor-reported) [4, 5].

### 3.3 Coding gap between Flash and the flagship

Table 2. Ampere.sh side-by-side (Aug 2026), both models at reasoning effort (third-party benchmark) [3].

| Benchmark | GLM-5.3-Flash | GLM-5.3 |
| --- | ---: | ---: |
| Terminal Bench | 84.3 | 88.2 |
| DeepSWE v1 | 63.4 | 66.9 |
| AutomationBench | **48.8** | 48.2 |
| AA Intelligence Index | 57 | 60 |

Flash is slightly ahead on AutomationBench and a few points behind on Terminal Bench and DeepSWE [3]. The blended price gap from Table 1 is ~9x (2.15 / 0.24, derived). Ampere's own conclusion: *"whether those extra few benchmark points justify paying roughly nine times more per token… For many production coding agents, they may not."* [3] Ampere also reports that Flash wins for visual coding / browser-use / computer-use workflows because it can see [3].

### 3.4 Alternatives for capability and throughput

- GLM-5.3 (II 45) is 3 points above Flash [9].
- Kimi K3 (II 44) at $3/$15 has the second-worst cost per point after GPT-5.5 [12, 13].
- Qwen3.8 Max (II 40) scores 2 points less than Flash at a higher blended price and 40 vs 60 tok/s [11]: 3.00 / 0.24 = 12.5x Flash's blended price and two-thirds the speed (derived).
- GLM-5.2 (II 39) has the same list price as the flagship GLM-5.3, scores 3 points below Flash, and is slower than the flagship (62 vs 71 tok/s) [14, 9].
- DeepSeek V4 Flash has the highest throughput of the catalog's models apart from Gemini 3.5 Flash in Table 1, 126 tok/s, rank 7/112 on AA's speed chart [7], at 2.8x Flash's blended price (0.66 / 0.24, derived) and 13.5 vs 6.7 USD per Index point.

## 4. Discussion

### 4.1 Principal findings

RQ1: on AA's data GLM-5.3-Flash is the most cost-efficient model on the catalog by a wide margin, not a marginal one; the nearest competitor costs about twice as much per Index point (Table 1). Its low price is consistent with its sparse architecture (18B of 320B parameters active per token) [4, 5].

RQ2: the coding gap to the flagship is small while the price gap is ~9x. Flash trails by a few points on Terminal Bench and DeepSWE, which is a deficit rather than a collapse, and leads on agentic automation [3]. This rests on a single third-party comparison.

RQ3: GLM-5.3 (+3 Index points) is the only sensible capability upgrade on this catalog; every other model is worse value per point. Kimi K3 has similar raw intelligence but poor value; Qwen3.8 Max is more expensive, less capable and slower than Flash; GLM-5.2 is strictly dominated by GLM-5.3-Flash. DeepSeek V4 Flash is the throughput option: cheap in absolute terms, but worth choosing only for long high-volume batch jobs where wall-clock time dominates token cost.

### 4.2 Comparison with prior work

Ampere.sh reaches the same conclusion for production coding agents: the extra benchmark points of the flagship may not justify roughly nine times the per-token price [3]. Ampere's Index figures (57 and 60) differ from AA's page values (42 and 45) [6, 9]; the report does not record which Index version each uses, and the gap between the two models (3 points) is the same in both.

### 4.3 Practical implications

- Keep `z-ai/glm-5.3-flash` as the Hermes daily driver and omp `@smol` model; the current configuration (Table 3) needs no change.
- Flash's one inefficiency is verbosity at max effort (180M suite tokens, rank 25/112) [6]. If quota burn becomes a concern, dropping trivial calls from `max` to `high` effort costs little quality. The pi-commandcode-provider catalog for `z-ai/glm-5.3-flash` exposes effort levels `low, high, max` only; there is no `xhigh`.
- Re-run the scrape before relying on this for a purchase decision.

Table 3. Configuration observed as verified working on 2026-09-08.

| Surface | Setting |
| --- | --- |
| Hermes daily driver | `z-ai/glm-5.3-flash` via `commandcode` provider |
| omp `@smol` role | `commandcode/z-ai/glm-5.3-flash:max` (`~/.omp/agent/config.yml` → `modelRoles.smol`) |
| omp plugin | `pi-commandcode-provider@0.6.4` (`~/.omp/plugins`) |
| Auth | `COMMAND_CODE_API_KEY` in `~/.zshenv` (omp) / `COMMANDCODE_API_KEY` in `~/.hermes/.env` (Hermes) |

## 5. Limitations

- **List prices are not what CommandCode bills.** Prices are AA-tracked first-party list prices; on CommandCode you pay plan quota, not per-token, so quota burn depends on tokens consumed per task. Flash remains competitive on that measure (180M vs 210M and 240M suite tokens) [6, 9, 7], but per-task token use on real workloads was not measured.
- **Index comparability.** Intelligence Index scores between differently-benchmarked pages (different class medians) are approximately comparable only. The index version is given both as v4.3 (Section 2.1) and as "v3.4.3-class" (Table 1 caption); which applies was not recorded.
- **Staleness.** CommandCode model availability rotates; this reflects the catalog as of 2026-09-08.
- **Single sources.** The coding comparison (Table 2) comes from one third-party blog [3]; AA is the single source for Index scores and throughput, with OpenRouter cross-checking prices for only two models [1, 2].

## 6. Conclusion

GLM-5.3-Flash should remain the daily driver: on AA's data it costs $6.7 per Intelligence Index point, about half the next-best model and roughly 8x less than its own flagship, while trailing the flagship by only a few coding-benchmark points. GLM-5.3 is the upgrade path if more capability is needed, and DeepSeek V4 Flash the choice for throughput-bound batch work.

## Data and code availability

Scraped metrics and computed efficiency ratios (blend pricing, suite-cost-per-II-point) are in the session scratch files under `/tmp/aa-*.json`; the raw Artificial Analysis page text is preserved in `/tmp/aa-raw.json` for audit.

## References

[1] OpenRouter, Z.ai: GLM 5.3 (pricing cross-check): <https://openrouter.ai/z-ai/glm-5.3>
[2] OpenRouter, MoonshotAI: Kimi K3 (pricing cross-check): <https://openrouter.ai/moonshotai/kimi-k3>
[3] Ampere.sh, GLM 5.3 vs GLM 5.3 Flash: Benchmarks, Price & Coding (Aug 27, 2026): <https://www.ampere.sh/blog/glm-5-3-vs-glm-5-3-flash>
[4] Z.ai Developer Docs, GLM-5.3-Flash overview: <https://docs.z.ai/guides/llm/glm-5.3-flash>
[5] Hugging Face, zai-org/GLM-5.3-Flash model card: <https://huggingface.co/zai-org/GLM-5.3-Flash>
[6] Artificial Analysis, GLM-5.3-Flash: Intelligence, Performance & Price Analysis: <https://artificialanalysis.ai/models/glm-5-3-flash>
[7] Artificial Analysis, DeepSeek V4 Flash 0731 (Reasoning, Max Effort): <https://artificialanalysis.ai/models/deepseek-v4-flash>
[8] Artificial Analysis, DeepSeek V4 Pro 0813 (Reasoning, Max Effort): <https://artificialanalysis.ai/models/deepseek-v4-pro>
[9] Artificial Analysis, GLM-5.3: Intelligence, Performance & Price Analysis: <https://artificialanalysis.ai/models/glm-5-3>
[10] Artificial Analysis, Gemini 3.5 Flash: <https://artificialanalysis.ai/models/gemini-3-5-flash>
[11] Artificial Analysis, Qwen3.8 Max: <https://artificialanalysis.ai/models/qwen3-8-max>
[12] Artificial Analysis, Kimi K3 (max): <https://artificialanalysis.ai/models/kimi-k3>
[13] Artificial Analysis, GPT-5.5: <https://artificialanalysis.ai/models/gpt-5-5>
[14] Artificial Analysis, GLM-5.2: <https://artificialanalysis.ai/models/glm-5-2>
[15] Ampere.sh, GLM 5.3 Flash vs GPT-5.4 Mini: <https://www.ampere.sh/blog/glm-5-3-flash-vs-gpt-5-4-mini>
