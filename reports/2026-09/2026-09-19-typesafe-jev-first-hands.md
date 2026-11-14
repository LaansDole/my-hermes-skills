# TypeSafe Jev — First-Hands Evaluation Report

- **Date:** 2026-09-19
- **Scope:** What Jev is, live API behavior under the user's allowlisted key, measured latency/cost/calibration, error shapes, and where it fits the user's tooling
- **Method:** Vendor blog + live docs fetched 2026-09-19 [1, 2]; 10 live API experiments (E1-E8) run against `POST https://api.typesafe.ai/v1/systemone` [3] with the user's key; latency = end-to-end wall clock from this machine (Vietnam, +07) incl. network; calibration probe n=10 (toy facts, NOT a domain benchmark)
- **Artifacts:** experiment script `/tmp/jev_experiments.py` (re-runnable); TypeSafe skill installed at `~/.hermes/skills/typesafe-ai` [4]

## Verdict

Jev is a decision-only model — send state + typed questions, get calibrated probabilities instead of generated text [1, 5] — and it does what it claims on first hands: ~0.9s end-to-end per call from Vietnam, ~$0.00004 for a 9-question fan-out (vendor price list [1], not metered on our side), perfect calibration on a 10-fact toy probe (MAE 0.018), clean typed errors (400/422), and fan-out batching that cut wall time 8.65x and tokens 4.29x vs sequential calls with no answer drift. It is not a chat model and cannot replace one [6]; it is a fast structured-decision primitive to sit beside an LLM. The TypeSafe agent skill is installed and its two warnings (fan out, don't invent request fields) [4] were both validated by the experiments.

## What Jev is

- TypeSafe AI: SF lab, out of stealth 2026-09-15, $40M seed [6, 5]. Founder Diogo Almeida (ex-OpenAI; RLHF co-inventor per InfoWorld) [7]. "System One" = Kahneman fast/automatic thinking; Jev named for economist W.S. Jevons (efficiency → more demand, not less) [1, 6].
- Trained with RLCD (Reinforcement Learning for Calibrated Decisions): probabilities are meant to match real-world outcome frequencies [1, 6]. Calibrated = across many calls, answers given p=0.9 should be right ~90% of the time [6]. Per-answer correctness is still not guaranteed.
- Never generates prose [6]. All answers in a request are sampled in parallel against the same state; questions cannot see each other's answers [8, 4].
- Current model: `jev-1.13.0` (what `jev-latest` resolved to in every response today). Aliases: `jev-latest`, `jev-preview` [6] — `jev-preview` ALSO resolved to `jev-1.13.0` today (E7), i.e. no separate preview build live right now.
- Pricing: $0.042/M input tokens, output free (vendor-claimed) [1, 9, 10]. Measured usage: a 9-question fan-out on a ~900-char state = 799 in / 232 out tokens → ~$0.00004/call at list price.
- Limits (vendor docs): state + all questions ~64k tokens total; state + longest single question ~32k; Choice ≤255 options; Score 2-10 levels [6, 5]. Rate-limit errors return 429 + Retry-After [5] (not hit today at our volume).

## Measured results (live, 2026-09-19)

| # | Experiment | Result |
| --- | --- | --- |
| E1 | Fan-out: 1 call, 9 mixed questions (Noul/Choice/Score) | 200 OK, 0.98s, 799 in / 232 out tok; sensible answers (urgent noul 0.99, department=billing conf 1.0, churn score 2.0 conf 1.0) |
| E2 | Same 9 questions as 9 sequential calls | 8.478s total (mean 0.942s/call), 4428 tokens total → fan-out is 8.65x faster wall, 4.29x fewer tokens, answers equivalent |
| E3 | Calibration probe: 10 labeled yes/no facts, one call | MAE 0.018, Brier 0.001; all p within 0.05 of label. TOY probe (n=10, general facts) — says nothing about domain calibration |
| E4 | Confidence behavior | Clear question conf 1.0; ambiguous question still chose singapore conf 0.88 (wrong-ish: Quito is closer to the equator — real hallucination case caught, see findings); contextless score ("how happy is the writer?" with weather-only state) returned score 1.0 conf 0.99 — model fills defaults confidently when state lacks the dimension |
| E5 | Structured JSON state + backticked path refs (`ticket.messages[0].text`, `order.charges`) | All correct: refund_requested 0.99, policy_supports 0.99, n_charges=two conf 1.0 |
| E6 | Error shapes | Unknown model → 400 `{"detail":{"error_type":"api_usage_error",...}}`; empty questions → 422 FastAPI validation (min_length 1); bad question type → 400 "Invalid request." |
| E7 | `jev-preview` alias | Resolves to the SAME `jev-1.13.0` as `jev-latest` today |
| E8 | Response headers | `server: istio-envoy`, `x-typesafe-request-id: req_...` — no rate-limit headers on non-throttled responses |

## Findings

1. **Fan-out is the idiomatic pattern and it delivers.** One call with all independent questions was 8.65x faster and 4.29x cheaper than sequential single-question calls on identical state (measured). The docs' "speculative fan-out" advice [11] is real: batch every independent question, including ones only relevant for some inputs, and let code pick which answers to consume [8, 11].
2. **Calibration claim held on the toy probe** (MAE 0.018, Brier 0.001, n=10). This is the product's core bet [1]; a real calibration harness on YOUR domain data is the first serious experiment to build (see Next steps).
3. **Confidence ≠ probability, and both have blind spots.** Confidence is derived from distribution shape [12]. E4 caught two instructive cases: the model was wrong-but-confident on a geography comparison (0.88 on singapore over quito), and confidently defaulted (1.0) on a question whose state lacked the needed dimension. Calibrated ≠ correct per-call; never gate destructive actions on a single call [12].
4. **Noul has no confidence field** — the probability IS the signal [8]. Choice/Score carry confidence. Design question sets accordingly.
5. **Errors are typed and cheap to handle.** 400 = api_usage_error with message, 422 = FastAPI validation detail. Empty `questions` is a 422, not "no-op" — fail fast in client code.
6. **Latency from Vietnam is ~0.9s/call end-to-end** (vendor claims 70-500ms measured US West) [1, 6]. Still 3-300x faster than LLM-roundtrip workflows. Plan network latency into UX budgets.
7. **Version pinning matters**: `jev-latest` moved under us before (docs: jev-1.12 → 1.13) [6, 5]. If tuning thresholds, pin the versioned ID (`jev-1.13.0`) — the response's `model` field always reports what answered, so log it [5].
8. **Token metering includes output tokens for structured answers** (232 out on E1) even though pricing says output is "free" — usage is reported, cost is input-only.

## Where it fits the user's stack

- **Covidence screening (highest-leverage fit):** per-abstract Noul votes against PCC criteria with confidence gates — auto-Yes/auto-No at high confidence, human review for the middle band. The 81-unique set has known ground truth to calibrate against. Cost: cents for hundreds of abstracts.
- **Gate for coding agents:** the community `pi-jev-auto-mode` [13] / `jev-mcp` [14] pattern — deterministic rules first, Jev judges unvouched commands, fail closed when undecidable [13]. Directly applicable to omp/pi hooks.
- **Not a fit:** anything needing generation, reasoning chains, or open-ended answers — keep the LLM for that; Jev handles routing/scoring/verification/routing-policy decisions.

## Next steps (proposed, not started)

1. Real calibration harness on user-domain data (Covidence abstracts with known verdicts) — reliability bins + ECE, JSON + markdown report. This is the experiment that matters.
2. A small experiment CLI in a `~/Projects/jev-experiments` sibling repo (key in gitignored `.env`) — built via superpowers plan + `omp -p --model anthropic/claude-opus-5:xhigh` per standing workflow, when user says go.
3. If the harness holds up: wire a Jev gate into the Covidence full-text-review workflow as a first-pass sorter with confidence-gated escalation.

## Caveats

- Calibration probe is n=10 toy facts — directionally positive, statistically meaningless.
- Latency measured from Vietnam incl. network; vendor's 70-500ms is US-West-side [1, 6].
- All cost figures are vendor list price; we cannot see actual metering from the response.
- E4's wrong-confident geography answer is one sample — but it matches the docs' own warning that typed output guarantees the interface, not the truth [4, 6].
- `jev-preview` == `jev-latest` today; that may change any day.

## References

[1] TypeSafe blog, Introducing System One Models & Jev (2026-09-15): <https://typesafe.ai/blog/introducing-system-one-models-and-jev>
[2] TypeSafe docs index (fetched as llms.txt + .md pages, 2026-09-19): <https://docs.typesafe.ai/llms.txt>
[3] TypeSafe docs, Quick start (API shapes, request/response bodies): <https://docs.typesafe.ai/introduction/quickstart.md>
[4] typesafe-ai agent skill (GitHub typesafe-ai/skills; installed to ~/.hermes/skills/typesafe-ai): <https://github.com/typesafe-ai/skills/blob/main/skills/typesafe-ai/SKILL.md>
[5] DEV (valyuai), How to Use Jev: a practical guide (2026-09): <https://dev.to/valyuai/how-to-use-jev-a-practical-guide-to-typesafes-system-one-model-g5e>
[6] flaviocopes.com, A deep dive into Jev (2026-09): <https://flaviocopes.com/jev/>
[7] InfoWorld, TypeSafe AI's new models work with machines, not humans (2026-09): <https://www.infoworld.com/article/4223468/typesafe-ais-new-models-work-with-machines-not-humans.html>
[8] TypeSafe docs, Primitives (Noul/Choice/Score): <https://docs.typesafe.ai/primitives.md>
[9] Cloudflare AI docs, Jev (typesafe): <https://developers.cloudflare.com/ai/models/typesafe/jev/>
[10] Vercel AI Gateway, Jev: <https://vercel.com/ai-gateway/models/jev>
[11] TypeSafe docs, Speculative fan-out: <https://docs.typesafe.ai/patterns/fan-out.md>
[12] TypeSafe docs, Confidence: <https://docs.typesafe.ai/confidence.md>
[13] pi.dev, pi-jev-auto-mode (community gate for Pi coding agent): <https://pi.dev/packages/pi-jev-auto-mode>
[14] Glama, jev-mcp (MCP server for OpenCode/OMP/etc): <https://glama.ai/mcp/servers/minhgv/jev-mcp>
[15] TypeSafe Python SDK (TypeSafe docs; PyPI typesafe-sdk at <https://pypi.org/project/typesafe-sdk/>): <https://docs.typesafe.ai/sdk/python.md>
