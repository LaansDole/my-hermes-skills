# Persona A/B: does "You are a [role]" help current models?

This is the harness behind the report [Persona prompting on current models: A/B test and research](../../reports/2026-11/2026-11-14-persona-prompting-ab-test.md). It runs the same tasks under three system-prompt arms and scores the answers automatically.

| Arm | What is appended to omp's system prompt |
| --- | --- |
| `none` | Nothing. This is the control. |
| `expert` | A generic identity persona: "You are a world-class senior software engineer..." for code, and "You are a world-class expert in {category}..." for exam questions, matched to the question's subject. |
| `scoped` | No identity claim. A concrete brief instead: context, priorities, what to check, and the output contract. |

The exact texts are `EXPERT_CODE`, `SCOPED_CODE`, `EXPERT_MCQ` and `SCOPED_MCQ` in `bench.py`.

## Requirements

- `omp` on your PATH, logged in to providers that serve both models
- Python 3.10+ (standard library only)
- `../haiku-vs-luna-omp/` next to this folder: the coding fixtures, prompts and grading are reused from there

## Run

```bash
cd benchmarks/persona-ab
python3 bench.py                                      # 4 tasks x 3 arms x 2 models x 2 reps (MCQ = 14 batches per cell) = 204 runs
TASKS=hard,bughunt,fix REP_START=2 REPS=3 python3 bench.py   # add a third rep for the coding tasks
QFILE=fixtures/mmlupro-280.jsonl TASKS=mcq ARMS=none,expert REPS=1 python3 bench.py  # phase 2: 280 new questions, 56 batches
python3 analyze.py results.jsonl                      # summary tables + paired sign tests
TASKS=mcq ARMS=none,expert REPS=1 python3 bench.py    # a quick subset
```

| Variable | Default | Meaning |
| --- | --- | --- |
| `FABLE`, `LUNA` | `anthropic/claude-fable-5-2`, `opencode-go/gpt-6-luna` | omp model ids. `:<effort>` is added for you. |
| `EFFORT` | `medium` | Effort level for every run |
| `TASKS` | `hard,bughunt,fix,mcq` | Which tasks to run |
| `ARMS` | `none,expert,scoped` | Which prompt arms to run |
| `REPS`, `REP_START` | `2`, `0` | Rep indices `REP_START..REPS-1` are run |
| `PAR` | `6` | Runs in parallel |
| `OUT` | `$TMPDIR/persona-ab` | Where work copies, sessions and `results.jsonl` go (outside the repo, so omp doesn't load this repo's `AGENTS.md`) |

## Tasks

| Task | Source | Score |
| --- | --- | --- |
| hard, bughunt, fix | `../haiku-vs-luna-omp/fixtures/` (planted-defect review x2, make-the-tests-pass x1) | Same grading as that harness |
| mcq | `fixtures/mmlupro-70.jsonl`: 70 questions from [MMLU-Pro](https://huggingface.co/datasets/TIGER-Lab/MMLU-Pro) (MIT), 5 per category for all 14 categories, seed 20261114. Asked in same-category batches of 5, with no tools. | correct / 5 per batch |

## Run validity

- `omp-overlay.yml` turns off omp's advisor. With it on, a second model reviews each turn and injects notes, which would contaminate the arms.
- omp falls back to other models when a call fails, and an overlay can't switch that off. `bench.py` records every model that answered and every errored call. A run counts as valid only if every assistant message came from the requested model with no errors. Otherwise it retries, up to 3 attempts.
- Grading reads all of a run's assistant text, not only the last message, because a run can end with a short follow-up that refers back to the full answer.

## Data

`results-2026-11-14.jsonl` holds the 446 raw runs behind the report: phase 1 (222 runs, all arms, `mmlupro-70.jsonl`) followed by phase 2 (224 runs, `none` vs `expert`, `mmlupro-280.jsonl`, batch keys like `law#2`). `python3 analyze.py` reads it by default. `fixtures/mmlupro-280.jsonl` is 20 more questions per category (seed 20261115), with no overlap with the 70.
