# Does an expert persona in the system prompt help or hurt current models? An A/B test and literature review

- **Date:** 2026-11-14
- **Report type:** Benchmark study
- **Keywords:** persona prompting, system prompts, MMLU-Pro, Claude Fable 5.2, GPT-6 Luna, sign test
- **Data collected:** web research 2026-11-14; local A/B runs 2026-11-14.

## Abstract

**Background.** Many prompts and skills start with "You are a senior engineer" or "You are an expert in X". Earlier studies suggest such personas do not improve accuracy and can lower it, but current models may behave differently.
**Objective.** To test whether a generic expert persona, or a scoped brief without an identity claim, changes accuracy, cost or speed on current models, and to summarise what research and vendors now recommend.
**Methods.** A local A/B test ran 446 valid runs through `omp -p`, comparing three system-prompt arms (none, expert, scoped) on Claude Fable 5.2 and GPT-6 Luna at medium effort, on MMLU-Pro questions and planted-defect coding tasks [1, 2]. Paired MCQ answers were compared with an exact two-sided sign test. Two studies and a press report [3, 4, 5], vendor prompting docs [6, 7, 8] and two secondary syntheses [9, 10] were reviewed.
**Results.** With 420 paired MCQ answers per model, the expert persona changed accuracy by +1.0 pp on Fable (p = 0.34) and +0.2 pp on Luna (p = 1.00) (measured). Coding tasks scored 97-100% in every arm. Persona arms produced 10-25% more output tokens on coding runs. Prior work found no gain across 162 roles [5] and an accuracy loss on MMLU (68.0% vs 71.6%) [3].
**Conclusions.** A generic "You are a world-class expert" persona neither helped nor hurt either model in 446 runs: every accuracy difference was within noise (sign-test p ≥ 0.34). It is not a hindrance on these models, but it buys nothing and can be dropped from skills; roles that state scope, priorities and format remain worth keeping.

## 1. Introduction

Persona lines are a habit carried over from earlier models. Zheng et al. tested 162 roles on 4 model families and found that "adding personas in system prompts does not improve model performance" [5]. Hu, Rostami and Thomason (USC, March 2026 preprint) found that expert personas improve alignment but damage accuracy [3, 4]. Vendors still recommend a role, framed as scope [6, 7], and Anthropic advises reviewing prompts written for earlier models [8]. Whether a persona still matters on the models used daily here, Claude Fable 5.2 and the GPT-6 family, decides whether skills should keep these lines. GPT-6 Astra could not be tested, because no configured provider serves it; GPT-6 Luna stands in for the GPT-6 family.

- **RQ1.** Does an expert persona change accuracy on current models?
- **RQ2.** Does it change output length, speed or cost?
- **RQ3.** What do research and vendor guidance say about when roles help?

## 2. Methods

### 2.1 Sources and search strategy

Web research on 2026-11-14 covered 2 peer-reviewed or preprint studies [3, 5], press coverage of one [4], Anthropic and OpenAI prompting docs [6, 7, 8], and 2 secondary syntheses [9, 10]. Search terms and inclusion criteria were not recorded. MCQ items come from the MMLU-Pro dataset [2].

### 2.2 Evidence classification

- **Measured:** the local A/B runs (Tables 2 to 4) [1].
- **Third-party study:** Zheng et al. [5] (EMNLP Findings 2024) and Hu et al. [3] (preprint), with press coverage [4].
- **Vendor-reported:** Anthropic and OpenAI prompting guidance [6, 7, 8].
- **Secondary synthesis:** Learn Prompting [9] (anecdotal) and PromptForge [10].
- **Derived:** accuracy differences, sign-test p values, cost totals.

### 2.3 Experimental setup

Three arms were appended to omp's default system prompt; the exact texts are in `benchmarks/persona-ab/bench.py` [1].

Table 1. Experimental arms.

| Arm | Appended text |
| --- | --- |
| none | Nothing. This is the control. |
| expert | "You are a world-class senior software engineer with 20+ years of experience... you never miss a bug" for code. "You are a world-class expert in {subject}... You always get the right answer" for exam questions, matched to each question's subject. |
| scoped | No identity claim. A brief instead: the context, priorities in order, what to compare against, and the output format. |

Models: Claude Fable 5.2 and GPT-6 Luna, both at medium effort, run through `omp -p`. Tasks: MMLU-Pro questions with 10 options [2], and the planted-defect review and test-fixing coding tasks from the 2026-10-14 harness (3 tasks, 9 runs per arm). The MCQ set was run in two phases: phase 1 (140 answers per arm) and phase 2 (280 new questions for none and expert). omp's advisor was off for every run (`omp-overlay.yml`). Every run was checked to have been answered only by the requested model. One run retried after a network error. How the 446 runs map onto the MCQ answer counts (answers per run, number of reps) was not recorded.

### 2.4 Analysis

- Accuracy per arm = correct answers / answers; coding = fraction of defects found or tests passed.
- Each MCQ answer is paired with the control by question and rep; p is an exact two-sided sign test on the pairs where only one arm was right. Δ = arm accuracy - control accuracy, in percentage points.
- Wall time is reported as a median; output tokens and cost as means.
- Grading was automatic; the new harness grades all assistant text. One coding run was adjudicated by hand (Section 3.1).

## 3. Results

### 3.1 Accuracy (RQ1)

Table 2. Accuracy by arm (measured). MCQ = MMLU-Pro questions with 10 options [2]. Coding = the planted-defect review and test-fixing tasks from the 2026-10-14 harness.

| Model | Task | none | expert | scoped | Runs per arm |
| --- | --- | ---: | ---: | ---: | --- |
| Fable 5.2 | MCQ | 93.1% | 94.0% | 93.6% | 420 / 420 / 140 answers |
| Fable 5.2 | Coding (3 tasks) | 100%* | 100% | 100% | 9 runs |
| GPT-6 Luna | MCQ | 82.6% | 82.9% | 80.7% | 420 / 420 / 140 answers |
| GPT-6 Luna | Coding (3 tasks) | 100% | 97.2% | 100% | 9 runs |

*The automatic grader scored one Fable "none" review at 3/4. The answer did find the unlocked `get`, but wrote "`get` reads..." without the parentheses the regex expects; it was manually adjudicated to 4/4. Luna's one expert-arm miss (it did not report the unlocked `get`) is real.

Table 3. Paired MCQ comparison against the control (measured; p derived, exact two-sided sign test).

| Model | Arm | Answers | Control | Arm | Δ | Control right only | Arm right only | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Fable 5.2 | expert | 420 | 93.1% | 94.0% | +1.0 pp | 3 | 7 | 0.34 |
| Fable 5.2 | scoped | 140 | 92.9% | 93.6% | +0.7 pp | 2 | 3 | 1.00 |
| GPT-6 Luna | expert | 420 | 82.6% | 82.9% | +0.2 pp | 13 | 14 | 1.00 |
| GPT-6 Luna | scoped | 140 | 80.7% | 80.7% | +0.0 pp | 3 | 3 | 1.00 |

- In phase 1 (140 answers), the persona looked like a +4.3 pp gain for Luna. In phase 2 (280 new questions), it was −1.8 pp.
- Per subject, Luna with the persona went +10 pp on law and −7 pp on math and health; each subject cell has only 30 answers. Fable's per-subject differences were 0 to +7 pp.
- Every arm scored 97-100% on the coding tasks for both models.

### 3.2 Cost and speed (RQ2)

Table 4. Cost and speed (measured); medians for wall time, means for output tokens and cost.

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

- The expert and scoped arms produced 10-25% more output tokens and took 2-4 s longer on coding runs.
- In phase 1 the Fable expert arm cost $0.137 per MCQ call vs $0.079 for none. Session logs show 2.5x more cache-write tokens, because the subject-matched persona creates 14 different system prompts, and each one must be written to the prompt cache. In phase 2, when each prompt was reused more, the two arms cost the same: $0.077 vs $0.075.

### 3.3 Research and vendor guidance (RQ3)

- **Personas and accuracy.** Zheng et al. (EMNLP Findings 2024) tested 162 roles on 4 model families and 2,410 factual questions. They found "adding personas in system prompts does not improve model performance," and which persona helps on a given question is "largely random" [5].
- **Personas, alignment and facts.** Hu, Rostami and Thomason (USC, March 2026 preprint) found an expert persona lowered MMLU accuracy (68.0% vs 71.6%). A "Safety Monitor" persona raised JailbreakBench refusals from 53.2% to 70.9%. Their advice: be specific when you care about alignment, and add nothing when you care about facts [3, 4].
- **Vendor guidance.** Anthropic's current best-practices page, which covers Fable 5.2, keeps a "Give Claude a role" section. Its example is "You are a helpful coding assistant specializing in Python." The same page says to replace "CRITICAL: You MUST..." with plain wording, because current models follow the system prompt closely enough to over-trigger [6]. OpenAI says to put tone and role guidance in the system message and task details in the user message [7].
- **Reviewing old prompts.** Anthropic's Fable 5.2 guide says instructions written for earlier models "raised cost, caused side effects, or no longer had an effect." It tells you to delete cautions whose reason no longer holds [8].
- **Secondary syntheses.** Learn Prompting (2024, anecdotal) [9] and PromptForge (2026) [10] both describe "act as a senior engineer" as a workaround for weaker models that frontier models no longer need, while roles still earn their place when they define expertise, tone and scope.

## 4. Discussion

### 4.1 Principal findings

RQ1: the expert persona had no measurable effect on accuracy for either model (Fable +1.0 pp, p = 0.34; Luna +0.2 pp, p = 1.00; 420 paired answers each). The phase-1 swing for Luna, which reversed in phase 2, shows how small samples move, which is why the pooled result is the one to trust; the per-subject swings are likewise noise. The coding tasks hit the ceiling, so the coding result is "no harm seen", not "no effect". The scoped brief did not change accuracy either, which is expected: the research places its value in alignment (format, priorities and project fit), and these tests only measure correctness.

RQ2: personas made answers slightly longer with no accuracy gain. The Fable MCQ cost gap is a caching artifact, not a persona cost.

### 4.2 Comparison with prior work

This does not reproduce the USC result: Hu et al. found expert personas lowered MMLU accuracy (68.0% vs 71.6%) [3, 4], while here neither model lost accuracy. The likely reason is model strength: both models here score 83-94% on harder MMLU-Pro questions, and strong models seem to ignore an identity line that carries no information. ASSUMPTION: this explanation is inferred and was not tested. The null result agrees with Zheng et al. [5] and with vendor guidance that treats a role as scope rather than as a performance lever [6, 7].

### 4.3 Practical implications

Table 5. Recommendation for skills and prompts.

| Pattern | Keep? | Why |
| --- | --- | --- |
| "You are a world-class / senior / expert X" with nothing else | Drop | No accuracy effect in 446 local runs or in Zheng et al. [5]. USC found harm on weaker models [3]. It also adds output length. |
| A role used as scope ("You review PRs for a Rust CLI used by on-call SREs") | Keep | Anthropic still recommends it [6]. It carries real context. |
| Concrete priorities, constraints and output format | Keep | This is where the research finds gains: alignment and format [3]. It costs nothing in accuracy (no change here). |
| Persona for tone, voice, safety or refusal policy | Keep | USC measured alignment gains, e.g. +17.7 pp jailbreak refusals [3]. |
| "CRITICAL", "MUST", "never miss" wording | Soften | Current models over-trigger on it [6]. |

## 5. Limitations

- **GPT-6 Astra was not tested.** It isn't available through any configured provider (omp's model list, opencode). GPT-6 Luna, the smaller GPT-6 model, stands in. A model at Astra's level might behave like Fable more than Luna.
- **Medium effort only.** At high or max effort, more thinking could wash out the persona further, or change the result. That wasn't measured.
- **Ceiling effects.** The coding fixtures were saturated, and Fable's MCQ accuracy (93%) leaves little room to move. The test can rule out large effects, not small ones. With 420 pairs, a true ±2 pp effect could still be hidden.
- **Prompt context.** Personas were appended to omp's long coding-agent system prompt, not used as a bare system prompt. That matches how skills are used, but a persona sent as the entire system prompt might have a different effect.
- **Single persona texts.** The persona texts are single examples. The research shows the effect depends on which persona you use.
- **Grader issues in the reused 2026-10-14 harness** (`benchmarks/haiku-vs-luna-omp/bench.py`): (a) it grades only the last assistant message, which under-scores runs that end with a short follow-up; (b) the H2 regex misses "`get` reads..." without parentheses. The new harness grades all assistant text. The H2 regex is unchanged, and that one miss was adjudicated by hand. The 2026-10-14 results may have been affected by either issue.
- **Unrecorded design details.** The number of reps per question and the mapping of runs to answers were not recorded.

## 6. Conclusion

On Claude Fable 5.2 and GPT-6 Luna, a generic expert persona made no measurable difference to accuracy in 446 runs, added some output length, and so can be dropped from skills and prompts. Roles that carry real scope, priorities, format or tone remain useful, in line with vendor guidance and with research showing alignment rather than accuracy benefits.

## Data and code availability

Harness, fixtures and raw data: `benchmarks/persona-ab/` (`bench.py`, `analyze.py`, `results-2026-11-14.jsonl`) [1].

## References

[1] Local harness, fixtures and 446 raw runs (`bench.py`, `analyze.py`, `results-2026-11-14.jsonl`): <https://github.com/LaansDole/my-hermes-skills/tree/main/benchmarks/persona-ab>
[2] TIGER-Lab, MMLU-Pro dataset (Hugging Face): <https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro>
[3] Hu, Rostami, Thomason, "Expert Personas Improve LLM Alignment but Damage Accuracy: Bootstrapping Intent-Based Persona Routing with PRISM" (arXiv, Mar 2026): <https://arxiv.org/abs/2603.18507>
[4] The Register, "Telling an AI model that it's an expert makes it worse" (Mar 24, 2026): <https://www.theregister.com/software/2026/03/24/telling-an-ai-model-that-its-an-expert-makes-it-worse/5226049>
[5] Zheng et al., "When 'A Helpful Assistant' Is Not Really Helpful: Personas in System Prompts Do Not Improve Performances of LLMs" (EMNLP Findings 2024): <https://arxiv.org/abs/2311.10054>
[6] Anthropic, Prompting best practices (Claude Platform Docs): <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices>
[7] OpenAI, Prompting guide (API docs): <https://developers.openai.com/api/docs/guides/prompting>
[8] Anthropic, Prompting Claude Fable 5.2: <https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-2>
[9] Learn Prompting, "Revisiting Roles in Prompting" (Schulhoff, Aug 2024): <https://learnprompting.org/docs/intermediate/revisiting_roles>
[10] PromptForge, "Best Practices for Prompting Frontier AI Systems" (Bagalman, May 2026): <https://github.com/mbagalman/PromptForge/blob/main/guides/prompting-best-practices-2026.md>
