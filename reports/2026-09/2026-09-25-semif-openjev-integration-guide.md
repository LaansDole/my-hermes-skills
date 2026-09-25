# SemIf (formerly OpenJev): Integration and API Guide

- **Date:** 2026-09-25
- **Scope:** How to install, run, integrate, and safely consume TheoLeeCJ/SemIf, formerly OpenJev.
- **Method:** Web search plus source inspection of repository commit `23cf1f39fc9534fe81437200959b6dfc7106e45a`, fetched 2026-09-25. Commands and schemas below were checked against that commit's implementation, not inferred from similarly named projects.

---

## Verdict

SemIf is currently a local Python research package and JSONL command-line scorer, not a hosted service or a ready-made HTTP API. Integrate it through `semif-score` for batch or subprocess use, or call its Python scorer functions inside a long-lived worker; if an application needs HTTP, place a small service around that worker rather than expecting a built-in `/v1/systemone` endpoint.[1][4]

The project was formerly named OpenJev, but it is independent of TypeSafe and does not reproduce TypeSafe's undisclosed Jev model or training.[2] This distinction also matters because other, newer projects use the OpenJev name and expose different APIs.

---

## 5-minute overview

You send three things: the `state` holding the evidence, one `question`, and 2-16 explicitly described options.[5] SemIf labels those options with answer-token letters, then reads the model's last-position logits for exactly those letters and applies softmax over them.[6] Nothing is written back: there is no decoding loop, no prose to parse, and no JSON to repair or retry.

That is where the speed comes from. Scoring is a forward pass over the prompt instead of token-by-token generation, and `shared` mode prefills one long state once and reuses that prefix across every independent question asked about it.[8]

Decision quality comes from the bounded, explicit option set — the model chooses among alternatives you wrote down, including an explicit insufficient-evidence option when you supply one — and from validating that set on your own workload. It does not come from typed output alone.

The returned values are conditional scores over the options you supplied, not deployment confidence. They are relative to that option set and must be calibrated on representative labeled data before any action threshold is attached to them.[6][11]

---

## 1. What SemIf Does

SemIf turns one item of state plus one runtime-defined question and 2-16 described options into a probability distribution over those options.[5] It reads the language model's next-token logits for letter slots (`A` through `P`) and applies softmax; it does not generate an answer sentence or JSON response.[6]

Typical uses:

- route a support request;
- decide whether evidence supports a claim;
- select an application action from an allowlist;
- classify or rank a bounded set of alternatives;
- run many independent judgments over one shared, long state.

SemIf provides four execution modes:

| Mode | Purpose | State reuse | Supported backends |
| --- | --- | --- | --- |
| `direct` | Score each row independently | None | Torch, MLX, llama.cpp |
| `serial` | Process rows in order and reuse the immediately repeated state | One retained prefix cache | Torch, MLX, llama.cpp |
| `shared` | Evaluate a batch whose rows all have exactly the same state | One prefill, multiple question suffixes | Torch, MLX, llama.cpp |
| `reranker` | Alternative native reranker baseline | Backend-specific | Torch/CUDA only |

The CLI rejects MLX or llama.cpp with `reranker`; the Torch reranker is CUDA-only.[4]

---

## 2. Important Naming Boundary

Use these identifiers to avoid integrating the wrong project:

| Name | Meaning in this guide |
| --- | --- |
| SemIf | `github.com/TheoLeeCJ/SemIf`, package `semif-phase1`, CLI `semif-score` |
| Former OpenJev | The previous name of the same TheoLeeCJ/SemIf project |
| TypeSafe Jev | A separate hosted commercial model and API |
| `openjev/openjev` | A different open-weights project that now uses the OpenJev name |
| `api.openjev.sh` | A separate hosted API, not the SemIf CLI documented here |

Do not point a SemIf client at an OpenJev or TypeSafe endpoint and assume semantic or calibration equivalence. SemIf's own output explicitly labels its probabilities as conditional option scores and uncalibrated decision confidence.[6]

---

## 3. Requirements

The researched package declares Python 3.10 or newer and pins Torch 2.10.0, Transformers 5.17.0, Accelerate 1.12.0, Safetensors 0.8.0, Hugging Face Hub 1.31.0, Tokenizers 0.23.2, NumPy 2.2.6, SentencePiece 0.2.1, and Protobuf 7.36.1.[3]

Choose one runtime:

| Runtime | Recommended use | Notes |
| --- | --- | --- |
| Torch + CUDA | Main GPU path | Expose exactly one CUDA GPU; Qwen3.5-4B BF16 must fit in memory.[2][5] |
| MLX | Apple Silicon | Text scoring through Metal; direct, serial, and shared modes.[9][10] |
| Torch + MPS | Apple Silicon fallback | Supported, but some Qwen3.5 kernels use slower fallback paths.[9] |
| llama.cpp | CPU/local GGUF | Requires the `llamacpp` extra and a local GGUF checkpoint.[2][4] |
| Torch + CPU | Full-precision reference | Explicitly pass `--device cpu --dtype float32`; expect it to be slow.[2][4] |

The default Qwen3.5-4B MLX source weights are about 9 GB on disk and require additional execution memory.[10]

---

## 4. Installation

Clone the repository because SemIf is not presented as a stable PyPI SDK:

```bash
git clone https://github.com/TheoLeeCJ/SemIf.git
cd SemIf
git checkout 23cf1f39fc9534fe81437200959b6dfc7106e45a
python3 -m venv .venv
source .venv/bin/activate
```

Install the runtime you need:

```bash
# Torch: CUDA, MPS, or explicit CPU
pip install -e '.[test]'

# Apple Silicon MLX
pip install -e '.[test,mlx]'

# llama.cpp with a local GGUF
pip install -e '.[test,llamacpp]'
```

For a production integration, pin both the SemIf commit and model revision. Remote model revisions must be immutable 40-character commit IDs; local model directories require a nonempty revision or manifest label.[5]

Optional: put Hugging Face downloads on a large drive before installation or first use:

```bash
export HF_HOME=/path/to/large-drive/huggingface
```

---

## 5. Input API: JSONL Decision Rows

`semif-score` reads newline-delimited JSON. Each line is one independent decision:

```json
{
  "id": "route-1",
  "state": "Customer cannot access an account after a password reset.",
  "question": "Which queue should handle this request?",
  "options": [
    {"id": "access", "description": "Account access support."},
    {"id": "billing", "description": "Billing support."},
    {"id": "insufficient", "description": "There is not enough evidence to decide."}
  ]
}
```

### Field reference

| Field | Type | Required | Constraints and meaning |
| --- | --- | --- | --- |
| `id` | string | Yes | Nonempty decision identifier; maps output back to application code. Must be unique within a `shared` batch. |
| `state` | string, object, or array | Yes | Nonempty, finite JSON-compatible evidence and context. Objects and arrays retain structured JSON in direct modes. |
| `question` | string | Yes | Nonempty criterion to apply to the state. It must be self-contained. |
| `options` | array | Yes | 2-16 entries. Order is mapped to answer-token letters, so preserve it when comparing runs. |
| `options[].id` | string | Yes | Application-facing option ID; unique within the row. |
| `options[].description` | string | Yes | Meaning the model judges. Descriptions may be empty under the current validator, but meaningful descriptions are required for useful behavior. |

These constraints come directly from `validate_row` in the researched source.[5]

### Design rules

1. Put facts and evidence in `state`; put the single judgment in `question`.
2. Keep each question narrow and independently answerable.
3. Describe every option explicitly; IDs are for application code, not model semantics.
4. Include an `insufficient`, `unknown`, or `none` option when the evidence may not support any substantive answer.
5. Do not pass a URL and expect browsing. Fetch external content in your application and place the relevant content in `state`.
6. Keep policy and execution in code. SemIf should choose among allowed alternatives, not invent operations.

---

## 6. CLI API

The installed executable is `semif-score`.[3]

### Full command shape

```text
semif-score \
  --mode direct|serial|shared|reranker \
  --backend torch|mlx|llamacpp \
  --model MODEL_OR_LOCAL_PATH \
  --revision IMMUTABLE_REVISION_OR_LOCAL_LABEL \
  --input INPUT.jsonl \
  --output NEW_OUTPUT.jsonl \
  [--max-tokens 4096] \
  [--device auto|cuda|mps|cpu] \
  [--dtype bfloat16|float16|float32] \
  [--mlx-bits 4|8] \
  [--mlx-cache-limit-mib N] \
  [--gguf /path/to/model.gguf] \
  [--llama-threads N]
```

The output path must not already exist. SemIf creates it exclusively and refuses to overwrite it. Input that exceeds `--max-tokens` fails rather than being truncated.[4][6]

### CUDA example

```bash
CUDA_VISIBLE_DEVICES=0 semif-score \
  --mode direct \
  --model Qwen/Qwen3.5-4B \
  --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --input decisions.jsonl \
  --output results.jsonl
```

### Apple Silicon MLX example

```bash
semif-score \
  --backend mlx \
  --mode direct \
  --model Qwen/Qwen3.5-4B \
  --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --input decisions.jsonl \
  --output results-mlx.jsonl
```

Use `--mlx-bits 8` or `--mlx-bits 4` for in-memory affine quantization. Quantization changes probabilities and must be evaluated separately; it does not create another model artifact.[10]

### Apple Silicon MPS example

```bash
semif-score \
  --mode direct \
  --device mps \
  --model Qwen/Qwen3.5-4B \
  --revision 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a \
  --input decisions.jsonl \
  --output results-mps.jsonl
```

### CPU llama.cpp example

First obtain a compatible local GGUF, then run:

```bash
semif-score \
  --backend llamacpp \
  --mode direct \
  --model Qwen/Qwen3.5-4B \
  --revision local-gguf-manifest-v1 \
  --gguf /models/Qwen_Qwen3.5-4B-Q4_K_M.gguf \
  --llama-threads 8 \
  --input decisions.jsonl \
  --output results-cpu.jsonl
```

The `--model` value remains relevant because prompt construction uses the reference tokenizer; `--gguf` supplies the local scoring weights.[2][4]

---

## 7. Output API

A direct-mode output line has this logical shape:[6]

```json
{
  "id": "route-1",
  "option_ids": ["access", "billing", "insufficient"],
  "probabilities": [0.82, 0.06, 0.12],
  "option_logits": [8.1, 5.5, 6.2],
  "input_tokens": 137,
  "forward_seconds": 0.24,
  "total_seconds": 0.25,
  "prompt_sha256": "...",
  "prompt_version": "direct-options-v1",
  "model": {
    "source": "Qwen/Qwen3.5-4B",
    "revision": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
    "dtype": "bfloat16",
    "device": "...",
    "torch_version": "...",
    "transformers_version": "..."
  },
  "readout": "native full-vocabulary last-position logits restricted to declared answer slots",
  "probability_status": "conditional option score; uncalibrated as decision confidence"
}
```

The numeric values above are illustrative; the field shape is source-derived.

### Output field reference

| Field | Meaning |
| --- | --- |
| `id` | Input row identifier. |
| `option_ids` | IDs in the exact order corresponding to `probabilities` and `option_logits`. |
| `probabilities` | Softmax over only the declared answer-slot logits; values sum approximately to 1. |
| `option_logits` | Raw selected next-token logits. Preserve these if you plan to apply temperature calibration later. |
| `input_tokens` | Prompt token count. |
| `forward_seconds` | Timed model-forward work for the selected execution path. |
| `total_seconds` | End-to-end row scoring time inside the scorer. |
| `prompt_sha256` | Hash of the rendered prompt, useful for reproducibility and cache checks. |
| `prompt_version` | Prompt contract identifier; currently `direct-options-v1`. |
| `model` | Model source, revision, runtime, device, precision, and possibly serving configuration. |
| `readout` | Description of the scoring path. |
| `probability_status` | Explicit warning about interpretation. |

Serial output adds fields such as `cache_hit`, `prefix_tokens`, cache/prefix timing, answer token IDs, and vocabulary diagnostics.[7] Shared output adds the same `shared_timing` object to every output row, including batch size, prefix length, prefill time, replication time, and suffix-forward time.[4][8]

### Safely selecting an answer

Never assume the highest probability is at the same array index across different row schemas. Pair the arrays from the same output object:

```python
best_index = max(range(len(result["probabilities"])),
                 key=result["probabilities"].__getitem__)
best_option_id = result["option_ids"][best_index]
best_probability = result["probabilities"][best_index]
```

Treat `best_probability` as a relative score among the supplied options until calibrated on your workload.

---

## 8. Integration Pattern A: Batch Files

Use the CLI directly when decisions can be prepared and consumed in batches.

```python
import json
import subprocess
import tempfile
from pathlib import Path

MODEL = "Qwen/Qwen3.5-4B"
REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"


def score_batch(rows: list[dict]) -> list[dict]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "input.jsonl"
        destination = root / "output.jsonl"
        source.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
            encoding="utf-8",
        )
        subprocess.run(
            [
                "semif-score",
                "--mode", "direct",
                "--model", MODEL,
                "--revision", REVISION,
                "--input", str(source),
                "--output", str(destination),
            ],
            check=True,
        )
        return [
            json.loads(line)
            for line in destination.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
```

This is simple but inefficient for request-per-decision serving because every process invocation reloads the model. Use it for offline pipelines, cron jobs, experiments, and reproducible evaluation—not a latency-sensitive HTTP route.

---

## 9. Integration Pattern B: Long-Lived Python Worker

For an application service, load the model once and reuse it. The Python functions are implementation-level APIs, not a separately versioned public SDK, so pin the repository commit and place them behind your own adapter.

### Direct scorer

```python
from semif_phase1.core import load_causal_model, validate_row
from semif_phase1.direct import score

MODEL = "Qwen/Qwen3.5-4B"
REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"

model, tokenizer, metadata = load_causal_model(
    MODEL,
    REVISION,
    device="cuda",       # or "mps" / "cpu"
    dtype="bfloat16",    # use float32 for explicit CPU reference work
)


def decide(row: dict) -> dict:
    validate_row(row)
    return score(model, tokenizer, row, metadata, max_tokens=4096)
```

### Serial prefix reuse

Use serial mode when consecutive requests often share the same exact state:

```python
from semif_phase1.serial import SerialPrefixScorer

scorer = SerialPrefixScorer(model, tokenizer, metadata, max_tokens=4096)
result_a = scorer.score(row_a)
result_b = scorer.score(row_b)  # cache hit only if state matches
```

The scorer retains one state's native prefix cache. A changed state invalidates it.[7]

### Shared-state fan-out

Use shared scoring when many independent questions all see the exact same state:

```python
from semif_phase1.shared import score_shared

results, timing = score_shared(
    model,
    tokenizer,
    rows_with_identical_state,
    metadata,
    max_tokens=4096,
)
```

All rows must have exactly equal states and unique IDs. Questions are independent; one question cannot consume another question's result in the same call.[8]

### Concurrency

Do not call one mutable model/cache object concurrently without an explicit queue or lock. The llama.cpp backend owns one stateful scoring context, and serial/shared paths manipulate prefix caches.[2][7][8] A safe starting architecture is one worker queue per loaded model/device, with bounded input and application-level timeouts.

---

## 10. Integration Pattern C: Your Own HTTP API

SemIf does not ship an HTTP server at the researched commit.[1][3][4] If you need one, expose a narrow adapter around the long-lived worker.

Recommended contract:

```text
POST /v1/decisions
Content-Type: application/json

{
  "mode": "direct",
  "decisions": [<SemIf decision row>, ...]
}
```

Recommended response:

```text
200 OK

{
  "results": [<SemIf output row>, ...],
  "model_revision": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
}
```

Adapter requirements:

1. Validate every row with `validate_row` before enqueueing it.
2. Allow only configured model and revision values; do not accept arbitrary Hugging Face repositories from public callers.
3. Cap body size, decision count, and prompt tokens.
4. Serialize or bound GPU work to avoid out-of-memory failures.
5. Return `422` for invalid rows, `429` for queue saturation, and `503` for unavailable workers.
6. Do not expose raw traceback, filesystem paths, model cache paths, or unrestricted local model loading.
7. Preserve `option_ids`, `probabilities`, `option_logits`, model metadata, and prompt hash in internal logs, subject to data-retention policy.
8. Authenticate the endpoint and terminate TLS before exposing it outside localhost.

This wrapper contract is a recommended integration design, not a SemIf-provided API.

---

## 11. Choosing Between `direct`, `serial`, and `shared`

```text
Are all questions known now and based on the exact same state?
  Yes -> shared
  No  -> Will consecutive decisions often use the exact same state?
           Yes -> serial
           No  -> direct
```

Use a second scoring call when:

- an earlier decision determines which evidence to retrieve;
- an earlier answer changes the options or question;
- application state changed after the first decision;
- a decision must be confirmed against new evidence.

Shared mode is not a chain-of-thought or dependency mechanism; it is independent fan-out over a common prefix.[8]

---

## 12. Confidence, Calibration, and Thresholds

Raw SemIf probabilities are conditional on the options supplied. They are not universally calibrated confidence values.[6][11]

Consequences:

- Adding or removing an option changes the probability distribution.
- A high score does not prove that the state contains sufficient evidence unless an insufficient-evidence option was available.
- A threshold copied from another workload is not justified.
- Typed output guarantees the response shape, not semantic correctness.

SemIf includes an offline scalar temperature-calibration script. Given labeled results containing `option_logits`, it applies:

```text
calibrated_probabilities = softmax(option_logits / T)
```

Because division by a positive temperature is monotonic, calibration changes confidence but not the selected argmax.[11]

Example application of an already selected temperature:

```bash
python benchmarks/calibrate.py \
  --predictions predictions.jsonl \
  --temperature 1.23 \
  --calibrated-out calibrated.jsonl
```

Fit and validate `T` on representative, labeled data from the actual deployment workload. Then choose thresholds based on consequences—for example, auto-route only above the measured review threshold and send other cases to a human or a stronger model.

---

## 13. Error Handling

SemIf is a local program, so errors appear as Python exceptions or a nonzero subprocess exit—not HTTP statuses.

| Failure | Likely cause | Handling |
| --- | --- | --- |
| Missing row fields | No `id`, `state`, `question`, or `options` | Reject before inference. |
| Invalid state | Empty, unsupported type, NaN, infinity, or non-JSON data | Normalize to finite JSON-compatible content. |
| Invalid options | Fewer than 2, more than 16, duplicate IDs, or malformed entries | Fix the schema. |
| Token limit exceeded | Rendered prompt is larger than `--max-tokens` | Reduce state intentionally; SemIf will not truncate it. |
| Remote revision rejected | Revision is not a 40-character commit hash | Resolve and pin an immutable model commit. |
| CUDA device error | Zero or multiple visible GPUs | Set `CUDA_VISIBLE_DEVICES` to exactly one GPU. |
| Existing output file | CLI is create-only | Choose a new output path or remove an abandoned file deliberately. |
| Unsupported mode/backend | Reranker selected with MLX, llama.cpp, MPS, or CPU | Use direct/serial/shared or Torch/CUDA reranker. |
| Out of memory | Model, batch, or suffix fan-out is too large | Reduce batch size, use serial mode, quantize where supported, or use a smaller model. |

For subprocess integration, capture `stderr`, set a timeout, check the exit status, and treat partial output as incomplete. The CLI flushes rows as it writes, so an interrupted run can leave a partial file.[4]

---

## 14. Security and Privacy

Local execution means decision state does not need to be sent to TypeSafe or another hosted inference API, but model downloads still contact Hugging Face unless weights are already local.[2][10]

Production checklist:

- pin SemIf and model commits;
- review upstream model licenses separately from SemIf's MIT code license;
- keep the scorer on a private host or network;
- never let untrusted callers select arbitrary model paths or revisions;
- validate body size and token count before GPU admission;
- redact sensitive state from logs while retaining non-sensitive reproducibility metadata;
- isolate model caches with appropriate filesystem permissions;
- apply timeouts and queue limits;
- evaluate prompt-injection-like content because `state` is untrusted model input;
- use application allowlists for downstream actions.

SemIf's repository code is MIT-licensed, while upstream models retain their own licenses.[2]

---

## 15. Testing an Integration

### Schema smoke test

```bash
PYTHONPATH=src python3 - <<'PY'
import json
from pathlib import Path
from semif_phase1.core import validate_row

rows = [
    json.loads(line)
    for line in Path("examples/decisions.jsonl").read_text().splitlines()
    if line.strip()
]
for row in rows:
    validate_row(row)
print(f"validated {len(rows)} rows")
PY
```

### Repository tests

After installing the selected extras:

```bash
pytest -q
```

### Application tests

Maintain a labeled suite that covers:

1. normal cases for every option;
2. insufficient-evidence cases;
3. ambiguous cases near review thresholds;
4. reordered options;
5. missing or adversarial evidence;
6. long inputs near the token limit;
7. repeated-state serial behavior;
8. shared batches with mixed states, which must fail;
9. model or runtime upgrades compared against the pinned baseline;
10. calibrated-threshold behavior, not only argmax accuracy.

Do not silently promote a new SemIf commit, Transformers version, model revision, quantization, prompt version, or backend. Compare choices, probability drift, calibration, latency, and memory before deployment.

---

## 16. Observability

Keep these output fields where policy permits:

- `id`;
- `option_ids` and selected option;
- raw and calibrated probabilities;
- `option_logits`;
- `prompt_sha256` and `prompt_version`;
- model source, revision, backend, dtype, and runtime versions;
- input token count;
- forward and total timing;
- cache hit and shared timing fields;
- final application action and later observed outcome.

The state itself may contain sensitive data. Store it only when necessary and under an explicit retention policy.

---

## 17. Deployment Checklist

- [ ] Pin SemIf commit.
- [ ] Pin model revision and tokenizer source.
- [ ] Select backend and precision explicitly.
- [ ] Validate rows before inference.
- [ ] Add an insufficient-evidence option where appropriate.
- [ ] Load the model once in a long-lived worker.
- [ ] Serialize or bound device concurrency.
- [ ] Set token, body, batch, queue, and time limits.
- [ ] Preserve output-to-option alignment.
- [ ] Fit calibration and action thresholds on deployment data.
- [ ] Add a review or fallback path.
- [ ] Log version and prompt metadata without leaking sensitive state.
- [ ] Re-evaluate every model, runtime, backend, prompt, or quantization change.
- [ ] Verify upstream model and application-use licenses.

---

## 18. Known Limitations

- The Python imports are implementation-level APIs and may change without SDK-style compatibility guarantees.
- The repository does not provide a built-in HTTP server at the researched commit.[1][3][4]
- Direct decisions support at most 16 options because the implementation uses `A` through `P` answer slots.[5]
- Inputs over the configured token limit fail; there is no automatic truncation.[6]
- Raw probabilities are not portable confidence thresholds.[6][11]
- `shared` requires exact state equality and independent questions.[8]
- MLX and MPS shared execution loops over independent suffixes rather than using CUDA's parallel suffix batch.[8][9]
- Backend, precision, and quantization can change probabilities or choices.[2][10]
- The project identifies itself as phase-one research code, not as a managed production service.[2][3]

---

## Sources

[1] https://github.com/TheoLeeCJ/SemIf/tree/23cf1f39fc9534fe81437200959b6dfc7106e45a — TheoLeeCJ/SemIf repository at researched commit
[2] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/README.md — SemIf README
[3] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/pyproject.toml — SemIf package manifest
[4] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/src/semif_phase1/cli.py — SemIf CLI source
[5] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/src/semif_phase1/core.py — SemIf core source
[6] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/src/semif_phase1/direct.py — SemIf direct scorer source
[7] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/src/semif_phase1/serial.py — SemIf serial scorer source
[8] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/src/semif_phase1/shared.py — SemIf shared scorer source
[9] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/APPLE_SILICON.md — SemIf Apple Silicon guide
[10] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/MLX.md — SemIf MLX guide
[11] https://github.com/TheoLeeCJ/SemIf/blob/23cf1f39fc9534fe81437200959b6dfc7106e45a/docs/CALIBRATION.md — SemIf calibration guide
