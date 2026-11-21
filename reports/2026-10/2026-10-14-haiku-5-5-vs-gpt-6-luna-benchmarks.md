# Which effort level should omp's small-model agents use? Claude Haiku 5.5 vs GPT-6 Luna effort-level benchmarks

- **Date:** 2026-10-14
- **Report type:** Benchmark study
- **Keywords:** Claude Haiku 5.5, GPT-6 Luna, reasoning effort, omp subagents, latency, cost
- **Data collected:** local runs on or before 2026-10-14 (exact run date not recorded); Artificial Analysis comparison fetched 2026-10-14; VulcanBench pages dated Sep and Oct 2026.

## Abstract

**Background.** omp delegates lookups, setup and reviews to small-model subagents, which were configured at the `:max` effort level. An earlier speed comparison of the two models at `:max` left open whether lower effort settings would serve these agents better.
**Objective.** To measure how effort level (medium, high, max) changes speed, quality and cost for Claude Haiku 5.5 and GPT-6 Luna on short omp agent tasks, and to compare with public long-task benchmarks.
**Methods.** A local harness ran 4 planted-defect and repository tasks x 2 models x 3 effort levels x 2 runs = 48 runs through `omp -p --mode json`, graded automatically [1]. Results were compared with VulcanBench Frontier v4 effort ladders [2, 3, 4] and the Artificial Analysis Intelligence Index [5, 6].
**Results.** Haiku:medium and Haiku:high scored 97% and 100% with median times of 18 s and 27 s, against 335 s and $0.203 per 8 runs for Haiku:max at the same 100% score (measured). Luna's median time stayed at 57-80 s across effort levels. On VulcanBench long tasks Haiku solved 22/23 at both xhigh and max, with xhigh cheaper ($0.84 vs $1.54 per task) [3]; Luna solved at most 12/23 [4].
**Conclusions.** Haiku 5.5 is the stronger model, but `:max` is the wrong setting for omp's small-model agents: Haiku at medium or high scored as well as Haiku:max on these tasks, ran 10-20x faster, and cost a tenth as much. Luna's speed barely changes with effort level, but it gives up quality on harder work.

## 1. Introduction

omp assigns models to its subagents (`scout`, `init`, `reviewer`, `sonic`) through `task.agentModelOverrides`. Haiku 5.5 and GPT-6 Luna were both set to `:max`, the highest effort level, on the assumption that more reasoning gives better results. An earlier report compared the two models at `:max` for speed in omp [7]. This study varies the effort level instead, on short agent tasks typical of subagent work, and checks the result against public benchmarks on long software tasks.

- **RQ1.** How do speed, quality and cost change with effort level for each model on short omp agent tasks?
- **RQ2.** Do public long-task benchmarks agree?
- **RQ3.** Which effort level should each omp subagent use?

## 2. Methods

### 2.1 Sources and search strategy

Measured data come from the local harness [1]. Public benchmarks: VulcanBench Frontier v4 pages for Haiku 5.5 versus frontier models [2], the Haiku 5.5 effort ladder [3] and the GPT-6 Luna effort ladder [4]; Artificial Analysis's comparison page [5] (fetched 2026-10-14; figures since updated) and its Haiku 5.5 launch article [6]. How the public sources were found was not recorded.

### 2.2 Evidence classification

- **Measured:** the 48 local runs (Tables 1 to 3) [1].
- **Third-party benchmark:** VulcanBench [2, 3, 4] and Artificial Analysis [5, 6].
- **Derived:** ratios in the text (for example 36.6k / 3.2k tokens = 11x).

### 2.3 Experimental setup

The harness ran each task through `omp -p --mode json` in a fresh session with a restricted tool set: 4 tasks x 2 models x 3 effort levels x 2 runs = 48 runs [1]. Six ran at a time. All 48 exited cleanly, and every run's session log confirms which model actually answered. Luna ran through the Command Code provider and Haiku through Anthropic. Hardware was not recorded.

Table 1. Task fixtures.

| Task | What it measures | Tools | How it was scored |
| --- | --- | --- | --- |
| hard | Review of a TTL cache plus a rate limiter with 4 planted defects: a deadlock from a non-reentrant lock, an unlocked `get`, an off-by-one in the limit, and a TTL refresh that turns the fixed window into a sliding one | read only | defects found / 4 |
| bughunt | Review of `orders.py` with 5 planted bugs: last page skipped, mutable default argument, SQL injection, float money math, swallowed exception | read only | bugs found / 5 |
| fix | Edit `textutil.py` until 7 unit tests pass (6 fail at the start) | read, edit, bash | tests passing / 7; 0 if the tests were edited |
| explore | Answer 3 factual questions about this repo | read only | facts correct / 3 |

### 2.4 Analysis

Grading was automatic: a regex match per planted defect, plus a real `unittest` run for the fix task. Misses were read through by hand. Score = mean fraction of defects, tests or facts found per setting. Times are medians, because six runs were affected by concurrency stalls (Section 5); with only two runs per cell, the per-task "median" is the average of two values. Cost per setting is the sum over its 8 runs; how cost was metered was not recorded.

## 3. Results

### 3.1 Local runs by effort level (RQ1)

Table 2. Overall results per setting, 8 runs each (measured).

| Setting | Median time | Avg output tokens | Avg turns | Score | Cost for 8 runs |
| --- | ---: | ---: | ---: | ---: | ---: |
| haiku-5-5:medium | **18 s** | 1.7k | 2.6 | 97% | $0.013 |
| haiku-5-5:high | 27 s | 3.2k | 3.0 | **100%** | $0.021 |
| haiku-5-5:max | 335 s | **36.6k** | 4.8 | 100% | $0.203 |
| gpt-6-luna:medium | 58 s | 1.9k | 8.0 | 97% | ~$0 |
| gpt-6-luna:high | 57 s | 1.8k | 7.8 | 100% | ~$0 |
| gpt-6-luna:max | 80 s | 2.5k | 8.6 | 100% | ~$0 |

Table 3. Median time per task in seconds (measured; two runs per cell, so noisy).

| Task | Haiku med | Haiku high | Haiku max | Luna med | Luna high | Luna max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hard | 20 | 26 | 861 | 55 | 57 | 86 |
| bughunt | 18 | 30 | 792 | 56 | 91 | 109 |
| fix | 24 | 29 | 813 | 88 | 44 | 602 |
| explore | 9 | 60 | 57 | 634 | 627 | 15 |

- **Haiku:max output.** Haiku:max wrote about 11x more output than Haiku:high (36.6k vs 3.2k tokens per run) and scored the same. On the three code tasks its fastest run took 274 s, while Haiku:high never went past 110 s on any task.
- **Turns.** Haiku at medium and high answers in 2-3 turns, while Luna takes about 8, making many small tool calls.
- **Misses.** The only misses were at medium. Haiku:medium missed the deadlock once, which is the hardest defect. Luna:medium missed the off-by-one once. Every high and max run, from both models, scored full marks.
- **Luna speed.** Luna's median was 57-80 s at every effort level.
- **Cost.** All 24 Haiku runs together cost $0.24, and 86% of that was Haiku:max. Luna showed near-zero cost on the Command Code plan.

### 3.2 Public benchmarks (RQ2)

Table 4. VulcanBench Frontier v4, 23 real software tasks per setting (third-party benchmark) [2, 3, 4].

| Effort | Haiku score | Haiku solved | Haiku min/task | Luna score | Luna solved | Luna min/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Low | 84.4 | 13/23 | 22.9 | 40.8 | 0/23 | 5.6 |
| Medium | 84.0 | 13/23 | 24.0 | 45.7 | 0/23 | 3.6 |
| High | 88.0 | 17/23 | 26.8 | 57.4 | 2/23 | 15.6 |
| Extra-high | 91.8 | 22/23 | **19.0** | 78.8 | 11/23 | 52.6 |
| Max | 92.2 | 22/23 | 27.7 | 81.4 | 12/23 | 60.5 |

- On full-size tasks, Haiku scores higher at every effort level [2]. Luna solves almost nothing below xhigh [4].
- Haiku's time per task changes little with effort. Its xhigh setting was both the fastest and the cheapest ($0.84 per task vs $1.54 at max), with the same 22/23 solved [3]. Max added +0.3 points for 46% more time and 83% more cost [3].
- Luna gets much slower at high effort: 3.6 min at medium vs 60 min at max [4].

Artificial Analysis puts Haiku 5.5 (max) above GPT-6 Luna (max) on its Intelligence Index, 43 vs 38 [5, 6]. Haiku also generates faster, but uses about 3.2x more output tokens per task [6], so a full answer takes about 3.5x longer [5]. Going from Haiku xhigh to max adds about 2 index points for about 1.8x the tokens [6].

## 4. Discussion

### 4.1 Principal findings

RQ1: Haiku:max spends most of its time thinking, not finding more; Haiku at medium and high is the fastest option overall, and Luna's many small tool calls mean even its quick runs need a minute. Effort level hardly changes Luna's speed, which fits the public data: Luna's extra effort shows up as more quality on hard tasks, not more speed. Haiku 5.5 is the stronger model in both the local runs and the public benchmarks.

### 4.2 Comparison with prior work

The local runs and VulcanBench differ on where extra effort stops paying. On short agent tasks like these, which take 2-8 turns, the cost of Haiku:max is pure thinking time, and the extra effort has nothing hard enough to pay off on. On VulcanBench's long tasks the extra reasoning does pay for itself up to xhigh, by solving more and avoiding dead ends [3]. In both sources, max is past the point of diminishing returns. The earlier `:max`-only speed report [7] measured the two models at a single effort level; this study adds the effort dimension.

### 4.3 Practical implications

RQ3: Table 5 gives the change applied in `~/.omp/agent/config.yml` (`task.agentModelOverrides`); the previous config is backed up. For long, multi-file tasks, use Haiku at xhigh rather than max: it's the best option on VulcanBench [3].

Table 5. omp subagent model settings before and after this study.

| omp agent | Before | Now | Why |
| --- | --- | --- | --- |
| scout | haiku-5-5:max | **haiku-5-5:medium** | Lookups and file finding. Medium answered explore questions in ~9 s. |
| init | haiku-5-5:max | **haiku-5-5:medium** | Project setup is short and well-structured. |
| reviewer | haiku-5-5:max | **haiku-5-5:high** | Medium missed the deadlock once and high never did. 27 s median. |
| sonic | gpt-6-luna:max | unchanged | Effort barely affects Luna's speed, and max protects quality. |

## 5. Limitations

- **Small sample:** 2 runs per cell, on small planted-defect tasks. This measures speed and basic correctness, not deep reasoning.
- **Stalls:** six runs took about 1,100-1,350 s: Haiku:max rep 2 on 3 tasks, Luna medium/high explore, and Luna:max fix. Their token counts were normal, so the wait was most likely queuing or rate limiting at the provider while 6 runs were in flight, not extra work. That is why the tables use medians; the per-task cells for those settings remain unreliable.
- **Different access paths:** Luna ran through the Command Code provider and Haiku through Anthropic, so network and queue latency differ.
- **Planted defects:** both models may have seen similar textbook bugs in training. The `hard` fixture is the most realistic of the four.
- **Cost basis:** Luna's ~$0 reflects a subscription plan, not per-token pricing, so the cost comparison is not like for like.
- **Public figures:** Artificial Analysis figures have since been updated [5]. VulcanBench's "+0.3 points" for max over xhigh is the source's figure; the rounded table values differ by 0.4 [3].

## 6. Conclusion

For omp's small-model agents, Haiku 5.5 at medium or high matches Haiku:max on quality while running 10-20x faster at a tenth of the cost, so `scout` and `init` moved to medium and `reviewer` to high. Luna's effort level barely affects its speed and was left at max. For long, multi-file work, Haiku at xhigh is the better setting than max.

## Data and code availability

Harness, fixtures and the 48 raw results: `benchmarks/haiku-vs-luna-omp/` in this repository; rerun with `python3 bench.py` (see its README) [1].

## References

[1] Local runs: harness, fixtures and the 48 raw results (rerun with `python3 bench.py`, see its README): <https://github.com/LaansDole/my-hermes-skills/tree/main/benchmarks/haiku-vs-luna-omp>
[2] VulcanBench, Frontier v4: Claude Haiku 5.5 vs frontier (Oct 2026): <https://vulcanbench.com/benchmarks/swe-v4-haiku55-vs-frontier.html>
[3] VulcanBench, Frontier v4: Claude Haiku 5.5 effort ladder (Oct 2026): <https://vulcanbench.com/benchmarks/swe-v4-haiku55-v324.html>
[4] VulcanBench, Frontier v4: GPT-6 Luna effort ladder (Sep 2026): <https://vulcanbench.com/benchmarks/swe-v4-gpt6-luna-v316.html>
[5] Artificial Analysis, Claude Haiku 5.5 vs GPT-6 Luna comparison (fetched 2026-10-14; figures since updated): <https://artificialanalysis.ai/models/comparisons/claude-haiku-5-5-vs-gpt-6-luna>
[6] Artificial Analysis, Anthropic has released Claude Haiku 5.5 (Oct 7, 2026): <https://artificialanalysis.ai/articles/claude-haiku-5-5>
[7] Earlier report, Haiku 5.5:max vs GPT-6 Luna:max speed in omp (2026-10-14): [2026-10-14-haiku-5-5-vs-gpt-6-luna-omp-speed.md](2026-10-14-haiku-5-5-vs-gpt-6-luna-omp-speed.md)
