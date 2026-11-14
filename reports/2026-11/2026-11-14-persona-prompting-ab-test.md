# Persona prompting on current models: A/B test and research

- **Date:** 2026-11-14
- **Scope:** Does starting a prompt or skill with "You are a senior engineer / an expert in X" still help current models, or does it hurt them?
- **Method:** Web research on 2026-11-14 (2 peer-reviewed or preprint studies, Anthropic and OpenAI prompting docs, 2 secondary syntheses). Local A/B test on 2026-11-14: 446 valid runs through `omp -p`, comparing three system-prompt arms on Claude Fable 5.2 and GPT-6 Luna at medium effort. Harness and raw data are in `benchmarks/persona-ab/`.

---

## Verdict

A generic "You are a world-class expert" persona neither helped nor hurt either model in 446 runs: every accuracy difference was within noise (sign-test p ≥ 0.34). So it is not a hindrance on these models, but it buys nothing, and you can drop it from skills. GPT-6 Astra could not be tested, because no configured provider serves it. GPT-6 Luna stands in for the GPT-6 family.

---

## A/B results

Three arms were appended to omp's default system prompt. The exact texts are in `benchmarks/persona-ab/bench.py`.

| Arm | Appended text |
| --- | --- |
| none | Nothing. This is the control. |
| expert | "You are a world-class senior software engineer with 20+ years of experience... you never miss a bug" for code. "You are a world-class expert in {subject}... You always get the right answer" for exam questions, matched to each question's subject. |
| scoped | No identity claim. A brief instead: the context, priorities in order, what to compare against, and the output format. |

Accuracy, measured. MCQ = MMLU-Pro questions with 10 options. Coding = the planted-defect review and test-fixing tasks from the 2026-10-14 harness.

| Model | Task | none | expert | scoped | Runs per arm |
| --- | --- | ---: | ---: | ---: | --- |
| Fable 5.2 | MCQ | 93.1% | 94.0% | 93.6% | 420 / 420 / 140 answers |
| Fable 5.2 | Coding (3 tasks) | 100%* | 100% | 100% | 9 runs |
| GPT-6 Luna | MCQ | 82.6% | 82.9% | 80.7% | 420 / 420 / 140 answers |
| GPT-6 Luna | Coding (3 tasks) | 100% | 97.2% | 100% | 9 runs |

\* The automatic grader scored one Fable "none" review at 3/4. I read the answer: it did find the unlocked `get`, but wrote "`get` reads..." without the parentheses the regex expects. Manually adjudicated to 4/4. Luna's one expert-arm miss (it did not report the unlocked `get`) is real.

Paired MCQ comparison against the control. Each answer is paired by question and rep, and p is an exact two-sided sign test on the pairs where only one arm was right.

| Model | Arm | Answers | Control | Arm | Δ | Control right only | Arm right only | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fable 5.2 | expert | 420 | 93.1% | 94.0% | +1.0 pp | 3 | 7 | 0.34 |
| Fable 5.2 | scoped | 140 | 92.9% | 93.6% | +0.7 pp | 2 | 3 | 1.00 |
| GPT-6 Luna | expert | 420 | 82.6% | 82.9% | +0.2 pp | 13 | 14 | 1.00 |
| GPT-6 Luna | scoped | 140 | 80.7% | 80.7% | +0.0 pp | 3 | 3 | 1.00 |

Cost and speed, measured. The table shows medians for wall time and means for output tokens and cost.

| Model | Task | Arm | Wall time | Output tokens | Cost per run |
| --- | --- | --- | ---: | ---: | ---: |
| Fable 5.2 | MCQ | none | 5.4 s | 354 | $0.076 |
| Fable 5.2 | MCQ | expert | 5.8 s | 418 | $0.097 |
| Fable 5.2 | coding | none | 19.3 s | 1,461 | $0.179 |
| Fable 5.2 | coding | expert | 22.1 s | 1,723 | $0.179 |
| Fable 5.2 | coding | scoped | 23.5 s | 1,833 | $0.196 |
| GPT-6 Luna | coding | none | 36.6 s | 2,824 | $0.004 |
| GPT-6 Luna | coding | expert | 41.1 s | 3,278 | $0.005 |

Total spend: $22.38. Fable cost $21.82 and Luna $0.56.

---

## Findings

1. **The expert persona had no measurable effect on accuracy for either model.** Fable: +1.0 pp (p = 0.34). Luna: +0.2 pp (p = 1.00). Both use 420 paired answers. In phase 1 (140 answers), the persona looked like a +4.3 pp gain for Luna. In phase 2 (280 new questions), it was −1.8 pp. Small samples swing like this, which is why the pooled result is the one to trust.
2. **This does not reproduce the USC result.** Hu et al. (March 2026) found expert personas lowered MMLU accuracy (68.0% vs 71.6%). Here neither model lost accuracy. The likely reason is model strength: both models here score 83-94% on harder MMLU-Pro questions, and strong models seem to ignore an identity line that carries no information. ASSUMPTION: this explanation is inferred and was not tested.
3. **Per-subject swings are noise.** Luna with the persona went +10 pp on law and −7 pp on math and health, but each subject cell has only 30 answers. Fable's per-subject differences were 0 to +7 pp.
4. **The coding tasks hit the ceiling.** Every arm scored 97-100% on both models. These fixtures can't separate the arms, so the coding result is "no harm seen", not "no effect".
5. **Personas made answers slightly longer.** The expert and scoped arms produced 10-25% more output tokens and took 2-4 s longer on coding runs, with no accuracy gain.
6. **The Fable MCQ cost gap is a caching artifact, not a persona cost.** In phase 1 the expert arm cost $0.137 per call vs $0.079 for none. Session logs show 2.5x more cache-write tokens, because the subject-matched persona creates 14 different system prompts, and each one must be written to the prompt cache. In phase 2, when each prompt was reused more, the two arms cost the same: $0.077 vs $0.075.
7. **The scoped brief didn't change accuracy either.** It isn't supposed to. The research below says its value is in alignment: format, priorities and project fit. These tests only measure correctness.

---

## What the research says

- **Personas don't make models more accurate.** Zheng et al. (EMNLP Findings 2024) tested 162 roles on 4 model families and 2,410 factual questions. They found "adding personas in system prompts does not improve model performance," and which persona helps on a given question is "largely random."
- **Personas help alignment and can hurt facts.** Hu, Rostami and Thomason (USC, March 2026 preprint) found an expert persona lowered MMLU accuracy (68.0% vs 71.6%). A "Safety Monitor" persona raised JailbreakBench refusals from 53.2% to 70.9%. Their advice: be specific when you care about alignment, and add nothing when you care about facts.
- **Vendors still recommend a role, but as scope.** Anthropic's current best-practices page, which covers Fable 5.2, keeps a "Give Claude a role" section. Its example is "You are a helpful coding assistant specializing in Python." That is a scope statement, not a flattery line. The same page says to replace "CRITICAL: You MUST..." with plain wording, because current models follow the system prompt closely enough to over-trigger. OpenAI says to put tone and role guidance in the system message and task details in the user message.
- **Old prompts should be reviewed for current models.** Anthropic's Fable 5.2 guide says instructions written for earlier models "raised cost, caused side effects, or no longer had an effect." It tells you to delete cautions whose reason no longer holds.
- **Secondary syntheses agree.** Learn Prompting (2024, anecdotal) and PromptForge (2026) both describe "act as a senior engineer" as a workaround for weaker models that frontier models no longer need. Roles still earn their place when they define expertise, tone and scope.

---

## Recommendation for skills and prompts

| Pattern | Keep? | Why |
| --- | --- | --- |
| "You are a world-class / senior / expert X" with nothing else | Drop | No accuracy effect in 446 local runs or in Zheng et al. USC found harm on weaker models. It also adds output length. |
| A role used as scope ("You review PRs for a Rust CLI used by on-call SREs") | Keep | Anthropic still recommends it. It carries real context. |
| Concrete priorities, constraints and output format | Keep | This is where the research finds gains: alignment and format. It costs nothing in accuracy (no change here). |
| Persona for tone, voice, safety or refusal policy | Keep | USC measured alignment gains, e.g. +17.7 pp jailbreak refusals. |
| "CRITICAL", "MUST", "never miss" wording | Soften | Current models over-trigger on it (Anthropic). |

---

## Caveats

- **GPT-6 Astra was not tested.** It isn't available through any configured provider (omp's model list, opencode). GPT-6 Luna, the smaller GPT-6 model, stands in. A model at Astra's level might behave like Fable more than Luna.
- **Medium effort only.** At high or max effort, more thinking could wash out the persona further, or change the result. That wasn't measured.
- **Ceiling effects.** The coding fixtures were saturated, and Fable's MCQ accuracy (93%) leaves little room to move. The test can rule out large effects, not small ones. With 420 pairs, a true ±2 pp effect could still be hidden.
- **Personas were appended to omp's long coding-agent system prompt**, not used as a bare system prompt. That matches how skills are used, but a persona sent as the entire system prompt might have a different effect.
- **The persona texts are single examples.** The research shows the effect depends on which persona you use.
- **Grader issues found in the reused 2026-10-14 harness** (`benchmarks/haiku-vs-luna-omp/bench.py`): (a) it grades only the last assistant message, which under-scores runs that end with a short follow-up; (b) the H2 regex misses "`get` reads..." without parentheses. The new harness grades all assistant text. The H2 regex is unchanged, and that one miss was adjudicated by hand. The 2026-10-14 results may have been affected by either issue.
- omp's advisor was off for every run (`omp-overlay.yml`). Every run was checked to have been answered only by the requested model. One run retried after a network error.

---

## References

- Local harness, fixtures and 446 raw runs (`bench.py`, `analyze.py`, `results-2026-11-14.jsonl`): <https://github.com/LaansDole/my-hermes-skills/tree/main/benchmarks/persona-ab>
- Zheng et al., "When 'A Helpful Assistant' Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of LLMs" (EMNLP Findings 2024): <https://arxiv.org/abs/2311.10054>
- Hu, Rostami, Thomason, "Expert Personas Improve LLM Alignment but Damage Accuracy: Bootstrapping Intent-Based Persona Routing with PRISM" (arXiv, Mar 2026): <https://arxiv.org/abs/2603.18507>
- The Register, "Telling an AI model that it's an expert makes it worse" (Mar 24, 2026): <https://www.theregister.com/software/2026/03/24/telling-an-ai-model-that-its-an-expert-makes-it-worse/5226049>
- Anthropic, Prompting best practices (Claude Platform Docs): <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
- Anthropic, Prompting Claude Fable 5.2: <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2>
- OpenAI, Prompting guide (API docs): <https://developers.openai.com/api/docs/guides/prompting>
- Learn Prompting, "Revisiting Roles in Prompting" (Schulhoff, Aug 2024): <https://learnprompting.org/docs/intermediate/revisiting_roles>
- PromptForge, "Best Practices for Prompting Frontier AI Systems" (Bagalman, May 2026): <https://github.com/mbagalman/PromptForge/blob/main/guides/prompting-best-practices-2026.md>
- TIGER-Lab, MMLU-Pro dataset (Hugging Face): <https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro>
