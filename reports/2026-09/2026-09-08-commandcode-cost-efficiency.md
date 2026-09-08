# CommandCode Model Efficiency Report

- **Date:** 2026-09-08
- **Scope:** Performance-per-cost analysis of the CommandCode Provider API model catalog, prompted by GLM-5.3-Flash being the daily-driver model in Hermes (and `@smol` role in omp).
- **Method:** SearXNG web search (self-hosted instance) → Artificial Analysis model pages (Intelligence Index v4.3, list prices, throughput) scraped via curl and parsed programmatically, supplemented by OpenRouter pricing pages, the Ampere.sh GLM-5.3-vs-Flash comparison, and vendor docs (Z.ai, Hugging Face).

---

## Verdict

**Keep GLM-5.3-Flash as the daily driver.** It is already the most cost-efficient model on the CommandCode catalog — by a wide margin, not a marginal one. No switch recommended.

---

## Efficiency Table

Sorted by Artificial Analysis' full Intelligence Index evaluation suite cost per Index point (their apples-to-apples efficiency measure). All prices are list prices per 1M tokens as tracked by Artificial Analysis (first-party serving, Sep 2026).

| Model | II[^1] | In $/1M | Out $/1M | Blend $/1M[^2] | Suite cost per II pt (USD) | tok/s | Params (total / active) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| **GLM-5.3-Flash** | **42** | **0.15** | **0.50** | **0.24** | **6.7** | 60 | 320B / 18B |
| DeepSeek V4 Flash | 35 | 0.44 | 1.32 | 0.66 | 13.5 | 126 | 284B / 13B |
| DeepSeek V4 Pro | 36 | 1.32 | 3.96 | 1.98 | 31.2 | 77 | 1.6T / 49B |
| GLM-5.3 | 45 | 1.40 | 4.40 | 2.15 | 55.6 | 71 | 753B / 40B |
| Gemini 3.5 Flash | 33 | 1.50 | 9.00 | 3.38 | 65.8 | 216 | n/a |
| Qwen3.8 Max | 40 | 2.00 | 6.00 | 3.00 | 79.3 | 40 | n/a |
| Kimi K3 | 44 | 3.00 | 15.00 | 6.00 | 83.1 | 42 | 2.8T / 104B |
| GPT-5.5 | 39 | 5.00 | 30.00 | 11.25 | 135.8 | 90 | n/a |
| GLM-5.2 | 39 | 1.40 | 4.40 | 2.15 | n/a | 62 | n/a |

[^1]: II = Artificial Analysis Intelligence Index v3.4.3-class score as published on each model page (higher is better; page-stated medians ranged 17–24 at fetch time).
[^2]: Blend = 3:1 input:output token mix, a standard workload approximation.

GLM-5.3-Flash is roughly **8x cheaper per quality point than its own flagship** (GLM-5.3) and ~20x cheaper per point than GPT-5.5.

---

## Findings

### 1. GLM-5.3-Flash profile

- Intelligence Index 42 (well above the class median of ~17); 1M context window; 60 tok/s output.
- Natively multimodal (vision) — the **only vision-capable GLM-5.3 variant**; the standard GLM-5.3 is primarily text-based. Vendor docs list input modality as Video / Image / Text / File.
- Sparse architecture: 320B total parameters with only 18B active per token, which is why it is this cheap to serve.

### 2. Coding gap to the flagship is small; the price gap is ~9x

Ampere.sh (Aug 2026) side-by-side, both at reasoning effort:

| Benchmark | GLM-5.3-Flash | GLM-5.3 |
| --- | ---: | ---: |
| Terminal Bench | 84.3 | 88.2 |
| DeepSWE v1 | 63.4 | 66.9 |
| AutomationBench | **48.8** | 48.2 |
| AA Intelligence Index | 57 | 60 |

- Flash is slightly **ahead** on agentic automation (AutomationBench), and the Terminal Bench / DeepSWE deficits are a few points, not a collapse.
- Ampere's own conclusion: *"whether those extra few benchmark points justify paying roughly nine times more per token… For many production coding agents, they may not."*
- Flash additionally wins for visual coding / browser-use / computer-use workflows because it can see.

### 3. If you ever want more headroom

- **GLM-5.3 (II 45, +3 pts)** is the only sensible upgrade on this catalog. Everything else is worse value per point.
- Kimi K3 (II 44) at $3/$15 is the worst value per point after GPT-5.5 — despite similar raw intelligence.
- Qwen3.8 Max (II 40) is ~2x flash's blended price for 2 points *less* intelligence, at roughly half the speed (40 vs 60 tok/s).
- GLM-5.2 is strictly dominated by GLM-5.3-Flash (same price as flagship, 3 fewer II points, slower).

### 4. Speed alternative

**DeepSeek V4 Flash** is the throughput king of the catalog (126 tok/s, rank 7/112 on AA's speed chart) at 2.8x flash's cost per point but still cheap in absolute terms. Consider it only for long high-volume batch jobs where wall-clock time dominates token cost.

---

## Caveats

- **Prices are AA-tracked first-party list prices.** On CommandCode you pay plan quota, not per-token — what actually matters for quota burn is tokens consumed per task. GLM-5.3-Flash is also competitive here: 180M tokens generated on AA's suite (verbose, rank 25/112) versus 210M for GLM-5.3 and 240M for DeepSeek V4 Flash.
- **Verbosity at max effort is flash's one inefficiency.** If quota burn ever becomes a concern, dropping trivial calls from `max` to `high` effort costs little quality. (Note: the pi-commandcode-provider catalog for `z-ai/glm-5.3-flash` exposes effort levels `low, high, max` only — there is no `xhigh`.)
- **CommandCode model availability rotates.** This reflects the catalog as of 2026-09-08; re-run the scrape before relying on it for a purchase decision.
- Intelligence Index scores between differently-benchmarked pages (different class medians) are approximately comparable only.

---

## Current configuration (verified working, no change needed)

| Surface | Setting |
| --- | --- |
| Hermes daily driver | `z-ai/glm-5.3-flash` via `commandcode` provider |
| omp `@smol` role | `commandcode/z-ai/glm-5.3-flash:max` (`~/.omp/agent/config.yml` → `modelRoles.smol`) |
| omp plugin | `pi-commandcode-provider@0.6.4` (`~/.omp/plugins`) |
| Auth | `COMMAND_CODE_API_KEY` in `~/.zshenv` (omp) / `COMMANDCODE_API_KEY` in `~/.hermes/.env` (Hermes) |

---

## References

- Artificial Analysis — GLM-5.3-Flash (Intelligence, Performance & Price): <https://artificialanalysis.ai/models/glm-5-3-flash>
- Artificial Analysis — GLM-5.3: <https://artificialanalysis.ai/models/glm-5-3>
- Artificial Analysis — DeepSeek V4 Flash 0731 (Reasoning, Max Effort): <https://artificialanalysis.ai/models/deepseek-v4-flash>
- Artificial Analysis — DeepSeek V4 Pro 0813 (Reasoning, Max Effort): <https://artificialanalysis.ai/models/deepseek-v4-pro>
- Artificial Analysis — Qwen3.8 Max: <https://artificialanalysis.ai/models/qwen3-8-max>
- Artificial Analysis — Kimi K3 (max): <https://artificialanalysis.ai/models/kimi-k3>
- Artificial Analysis — GPT-5.5: <https://artificialanalysis.ai/models/gpt-5-5>
- Artificial Analysis — Gemini 3.5 Flash: <https://artificialanalysis.ai/models/gemini-3-5-flash>
- Artificial Analysis — GLM-5.2: <https://artificialanalysis.ai/models/glm-5-2>
- Ampere.sh — GLM 5.3 vs GLM 5.3 Flash: Benchmarks, Price & Coding (Aug 27, 2026): <https://www.ampere.sh/blog/glm-5-3-vs-glm-5-3-flash>
- Z.ai Developer Docs — GLM-5.3-Flash overview: <https://docs.z.ai/guides/llm/glm-5.3-flash>
- Hugging Face — zai-org/GLM-5.3-Flash model card: <https://huggingface.co/zai-org/GLM-5.3-Flash>
- OpenRouter — GLM-5.3 pricing cross-check: <https://openrouter.ai/z-ai/glm-5.3>
- OpenRouter — Kimi K3 pricing cross-check: <https://openrouter.ai/moonshotai/kimi-k3>
- Ampere.sh — GLM 5.3 Flash vs GPT-5.4 Mini: <https://www.ampere.sh/blog/glm-5-3-flash-vs-gpt-5-4-mini>

*Scraped metrics and computed efficiency ratios (blend pricing, suite-cost-per-II-point) were computed live during the session; re-derive with the method above rather than relying on session scratch files.*
