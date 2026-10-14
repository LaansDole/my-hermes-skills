# Haiku 5.5 vs GPT-6 Luna in omp: benchmark harness

This is the harness behind the report [Claude Haiku 5.5 vs GPT-6 Luna: effort-level benchmarks in omp](../../reports/2026-10/2026-10-14-haiku-5-5-vs-gpt-6-luna-benchmarks.md). It runs four small agent tasks through [omp](https://github.com/can1357/oh-my-pi) (`omp -p --mode json`) for each model and effort level, then scores the answers automatically.

## Requirements

- `omp` on your PATH, logged in to providers that serve both models
- Python 3.10+ (standard library only)

## Run

```bash
cd benchmarks/haiku-vs-luna-omp
python3 bench.py                                   # full matrix: 4 tasks x 2 models x 3 efforts x 2 reps = 48 runs
TASKS=hard,fix EFFORTS=high REPS=1 python3 bench.py  # a quick subset
HAIKU=anthropic/claude-haiku-5-5 LUNA=openai/gpt-6-luna python3 bench.py  # use your own provider ids
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `HAIKU`, `LUNA` | `anthropic/claude-haiku-5-5`, `commandcode/gpt-6-luna` | omp model ids. `:<effort>` is added for you. |
| `TASKS` | `hard,bughunt,fix,explore` | Which tasks to run |
| `EFFORTS` | `medium,high,max` | Effort levels |
| `REPS` | `2` | Runs per cell |
| `PAR` | `6` | Runs in parallel. Lower it if your provider rate-limits: the report's 20-minute stalls came from 6 runs in flight. |
| `OUT` | `$TMPDIR/omp-bench` | Where work copies, sessions and `results.jsonl` are written (kept outside the repo, so omp doesn't load this repo's `AGENTS.md`) |
| `REPO` | this repo's root | Repo used for the `explore` task |

Each run appends one JSON line to `$OUT/results.jsonl` with the wall time, turns, output and reasoning tokens, cost, score, the model omp actually used, and the final answer.

## Tasks

| Task | Fixture | Score |
| --- | --- | --- |
| hard | `fixtures/hard/`: TTL cache plus rate limiter with 4 planted defects (deadlock, unlocked read, off-by-one, sliding-not-fixed window) | defects found / 4 |
| bughunt | `fixtures/bughunt/orders.py`: 5 planted bugs (skipped last page, mutable default, SQL injection, float money, swallowed exception) | bugs found / 5 |
| fix | `fixtures/fix/`: make `test_textutil.py` pass by editing `textutil.py` | tests passing / 7 (0 if the tests were edited) |
| explore | Three factual questions about this repo; the expected answers are read from the repo at run time | facts correct / 3 |

Review tasks are graded with regular-expression matches on the final answer (see `BUG_PATTERNS` and `HARD_PATTERNS` in `bench.py`). The patterns are deliberately loose; if your run scores a miss, read the answer before trusting it.

## Published data

`results-2026-10-14.jsonl` holds the 48 raw runs behind the report. Re-score it with the current grading code:

```bash
python3 -c "import bench,json; [print(r['task'],r['model'],r['effort'],bench.score(r['task'],r['final'],None)[0]) for r in map(json.loads,open('results-2026-10-14.jsonl')) if r['task']!='fix']"
```
