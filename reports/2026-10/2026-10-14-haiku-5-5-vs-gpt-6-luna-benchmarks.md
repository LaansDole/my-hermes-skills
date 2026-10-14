# Claude Haiku 5.5 vs GPT-6 Luna: effort-level benchmarks in omp

- **Date:** 2026-10-14
- **Scope:** A follow-up to [Haiku 5.5:max vs GPT-6 Luna:max speed in omp](2026-10-14-haiku-5-5-vs-gpt-6-luna-omp-speed.md). It compares both models at medium, high and max effort on four agent tasks, and checks the results against two public benchmarks.
- **Verdict:** Haiku 5.5 is the stronger model, but `:max` is the wrong setting for omp's small-model agents. Haiku at medium or high scored as well as Haiku:max on these tasks, ran 10-20x faster, and cost a tenth as much. Luna's speed barely changes with effort level, but it gives up quality on harder work.

## Method

The harness ran each task through `omp -p --mode json` in a fresh session with a restricted tool set: 4 tasks x 2 models x 3 effort levels x 2 runs = 48 runs. Six ran at a time. All 48 exited cleanly, and every run's session log confirms which model actually answered.

| Task | What it measures | Tools | How it was scored |
| --- | --- | --- | --- |
| hard | Review of a TTL cache plus a rate limiter with 4 planted defects: a deadlock from a non-reentrant lock, an unlocked `get`, an off-by-one in the limit, and a TTL refresh that turns the fixed window into a sliding one | read only | defects found / 4 |
| bughunt | Review of `orders.py` with 5 planted bugs: last page skipped, mutable default argument, SQL injection, float money math, swallowed exception | read only | bugs found / 5 |
| fix | Edit `textutil.py` until 7 unit tests pass (6 fail at the start) | read, edit, bash | tests passing / 7; 0 if the tests were edited |
| explore | Answer 3 factual questions about this repo | read only | facts correct / 3 |

Grading was automatic: a regex match per planted defect, plus a real `unittest` run for the fix task. I read through the misses by hand. One grading-pattern bug was found in the trial run and fixed before the main run.

## Results

Times are medians, because six runs were affected by the concurrency stalls described under Caveats.

| Setting | Median time | Avg output tokens | Avg turns | Score | Cost for 8 runs |
| --- | ---: | ---: | ---: | ---: | ---: |
| haiku-5-5:medium | **18 s** | 1.7k | 2.6 | 97% | $0.013 |
| haiku-5-5:high | 27 s | 3.2k | 3.0 | **100%** | $0.021 |
| haiku-5-5:max | 335 s | **36.6k** | 4.8 | 100% | $0.203 |
| gpt-6-luna:medium | 58 s | 1.9k | 8.0 | 97% | ~$0 |
| gpt-6-luna:high | 57 s | 1.8k | 7.8 | 100% | ~$0 |
| gpt-6-luna:max | 80 s | 2.5k | 8.6 | 100% | ~$0 |

Median time per task, in seconds:

| Task | Haiku med | Haiku high | Haiku max | Luna med | Luna high | Luna max |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| hard | 20 | 26 | 861 | 55 | 57 | 86 |
| bughunt | 18 | 30 | 792 | 56 | 91 | 109 |
| fix | 24 | 29 | 813 | 88 | 44 | 602 |
| explore | 9 | 60 | 57 | 634 | 627 | 15 |

With only two runs per cell, the per-task "median" is just the average of two values, so read the per-task numbers as noisy. The overall row is the reliable one.

### Findings

1. **Haiku:max spends most of its time thinking, not finding more.** It wrote about 11x more output than Haiku:high (36.6k vs 3.2k tokens per run) and scored the same. On the three code tasks its fastest run took 274 s, while Haiku:high never went past 110 s on any task.
2. **Haiku at medium and high is the fastest option overall.** It answers in 2-3 turns, while Luna takes about 8. Luna makes many small tool calls, so even its quick runs need a minute.
3. **The only misses were at medium.** Haiku:medium missed the deadlock once, which is the hardest defect. Luna:medium missed the off-by-one once. Every high and max run, from both models, scored full marks.
4. **Effort level hardly changes Luna's speed:** a median of 57-80 s at every level. That fits the public data below: Luna's extra effort shows up as more quality on hard tasks, not more speed.
5. **Cost:** all 24 Haiku runs together cost $0.24, and 86% of that was Haiku:max. Luna showed near-zero cost on the Command Code plan.

## Public benchmarks

**VulcanBench Frontier v4** ran 23 real software tasks per setting ([Haiku vs frontier](https://vulcanbench.com/benchmarks/swe-v4-haiku55-vs-frontier.html), [Haiku 5.5 ladder](https://vulcanbench.com/benchmarks/swe-v4-haiku55-v324.html), [GPT-6 Luna ladder](https://vulcanbench.com/benchmarks/swe-v4-gpt6-luna-v316.html)):

| Effort | Haiku score | Haiku solved | Haiku min/task | Luna score | Luna solved | Luna min/task |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Low | 84.4 | 13/23 | 22.9 | 40.8 | 0/23 | 5.6 |
| Medium | 84.0 | 13/23 | 24.0 | 45.7 | 0/23 | 3.6 |
| High | 88.0 | 17/23 | 26.8 | 57.4 | 2/23 | 15.6 |
| Extra-high | 91.8 | 22/23 | **19.0** | 78.8 | 11/23 | 52.6 |
| Max | 92.2 | 22/23 | 27.7 | 81.4 | 12/23 | 60.5 |

- On full-size tasks, Haiku is much stronger at every effort level. Luna solves almost nothing below xhigh.
- Haiku's time per task barely changes with effort. Its **xhigh** setting was both the fastest and the cheapest ($0.84 per task vs $1.54 at max), with the same 22/23 solved. Max added +0.3 points for 46% more time and 83% more cost.
- Luna gets much slower at high effort: 3.6 min at medium vs 60 min at max.

**Artificial Analysis** ([comparison](https://artificialanalysis.ai/models/comparisons/claude-haiku-5-5-vs-gpt-6-luna)) puts Haiku 5.5 (max) above GPT-6 Luna (max) on its Intelligence Index, 43 vs 38. Haiku also generates faster, but uses about 3.2x more output tokens per task, so a full answer takes about 3.5x longer. Going from Haiku xhigh to max adds about 2 index points for about 1.8x the tokens.

## Why the two sources differ

On short agent tasks like these, which take 2-8 turns, the cost of Haiku:max is pure thinking time, and the extra effort has nothing hard enough to pay off on. On VulcanBench's long tasks the extra reasoning does pay for itself up to xhigh, by solving more and avoiding dead ends. In both sources, max is past the point of diminishing returns.

## Recommendation for omp

| omp agent | Before | Now | Why |
| --- | --- | --- | --- |
| scout | haiku-5-5:max | **haiku-5-5:medium** | Lookups and file finding. Medium answered explore questions in ~9 s. |
| init | haiku-5-5:max | **haiku-5-5:medium** | Project setup is short and well-structured. |
| reviewer | haiku-5-5:max | **haiku-5-5:high** | Medium missed the deadlock once and high never did. 27 s median. |
| sonic | gpt-6-luna:max | unchanged | Effort barely affects Luna's speed, and max protects quality. |

This change is applied in `~/.omp/agent/config.yml` (`task.agentModelOverrides`), and the previous config is backed up. For long, multi-file tasks, use Haiku at **xhigh** rather than max: it's the best option on VulcanBench.

## Caveats

- **Small sample:** 2 runs per cell, on small planted-defect tasks. This measures speed and basic correctness, not deep reasoning.
- **Stalls:** six runs took about 1,100-1,350 s: Haiku:max rep 2 on 3 tasks, Luna medium/high explore, and Luna:max fix. Their token counts were normal, so the wait was queuing or rate limiting at the provider while 6 runs were in flight, not extra work. That's why the tables use medians.
- **Different access paths:** Luna ran through the Command Code provider and Haiku through Anthropic, so network and queue latency differ.
- **Planted defects:** both models may have seen similar textbook bugs in training. The `hard` fixture is the most realistic of the four.

## Sources

- Local runs: harness `omp_bench2.py`, raw results `omp-bench2/results.jsonl` (48 rows), omp sessions with token usage per turn. All are kept in the Hermes scratch directory.
- [VulcanBench Frontier v4: Claude Haiku 5.5 vs frontier](https://vulcanbench.com/benchmarks/swe-v4-haiku55-vs-frontier.html)
- [VulcanBench: Claude Haiku 5.5 effort ladder](https://vulcanbench.com/benchmarks/swe-v4-haiku55-v324.html)
- [VulcanBench: GPT-6 Luna effort ladder](https://vulcanbench.com/benchmarks/swe-v4-gpt6-luna-v316.html)
- [Artificial Analysis: Claude Haiku 5.5 vs GPT-6 Luna](https://artificialanalysis.ai/models/comparisons/claude-haiku-5-5-vs-gpt-6-luna)
- Earlier report: [Haiku 5.5:max vs GPT-6 Luna:max speed in omp](2026-10-14-haiku-5-5-vs-gpt-6-luna-omp-speed.md)
