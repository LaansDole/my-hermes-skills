#!/usr/bin/env python3
"""Persona A/B benchmark: does "You are a [role]" help or hurt current models?

Three system-prompt arms, appended to omp's default system prompt with --append-system-prompt:
  none    - nothing appended (control)
  expert  - generic identity persona ("You are a world-class senior engineer / expert in X")
  scoped  - no identity claim; a concrete brief: context, priorities, output contract

Tasks
  hard, bughunt, fix - coding fixtures reused from ../haiku-vs-luna-omp (same grading code)
  mcq               - 70 MMLU-Pro questions (5 per category x 14), asked in 14 same-category batches of 5,
                      no tools. The expert arm is domain-matched per batch. Score = correct / 5.
"""
import concurrent.futures as cf, importlib.util, json, os, re, shutil, subprocess, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
# Load the earlier harness by path: both files are named bench.py, so a plain import would load this file.
_spec = importlib.util.spec_from_file_location("base_bench", os.path.join(HERE, "..", "haiku-vs-luna-omp", "bench.py"))
base = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(base)  # reuses FIX, PROMPTS, TOOLS, score()

OUT = os.environ.get("OUT", os.path.join(os.environ.get("TMPDIR", tempfile.gettempdir()), "persona-ab"))
MODELS = {"fable": os.environ.get("FABLE", "anthropic/claude-fable-5-2"),
          "luna": os.environ.get("LUNA", "opencode-go/gpt-6-luna")}
EFFORT = os.environ.get("EFFORT", "medium")
REPS = int(os.environ.get("REPS", "2"))
TASKS = os.environ.get("TASKS", "hard,bughunt,fix,mcq").split(",")
ARMS = os.environ.get("ARMS", "none,expert,scoped").split(",")

EXPERT_CODE = ("You are a world-class senior software engineer with 20+ years of experience in Python, "
               "concurrency and security. You are meticulous and you never miss a bug.")
SCOPED_CODE = ("Context: this code belongs to a small internal Python service maintained by a three-person team. "
               "Reviews and fixes here prioritise, in order: correctness, concurrency safety, security, data "
               "integrity. Ignore style and naming. Compare behaviour against any spec or tests in the directory. "
               "For each problem give file:line, what breaks and when, and the smallest fix. "
               "Keep edits minimal and verify them by running the tests when tools allow it.")
EXPERT_MCQ = "You are a world-class expert in {cat} with decades of experience. You always get the right answer."
SCOPED_MCQ = ("Context: you are answering graded multiple-choice exam questions. Only the final letter is graded. "
              "Read every option before choosing; options can differ only in units, sign or a single qualifier. "
              "Work each problem out before committing to a letter.")

LETTERS = "ABCDEFGHIJ"
QFILE = os.environ.get("QFILE", os.path.join(HERE, "fixtures", "mmlupro-70.jsonl"))
QUESTIONS = [json.loads(l) for l in open(QFILE)]
BATCHES = {}  # batch key -> 5 questions from one category (key = category, or category#k for larger files)
_bycat = {}
for q in QUESTIONS:
    _bycat.setdefault(q["category"], []).append(q)
for c, qs in _bycat.items():
    for k in range(0, len(qs), 5):
        BATCHES[c if len(qs) <= 5 else f"{c}#{k // 5}"] = qs[k:k + 5]


def mcq_prompt(qs):
    parts = ["Answer these multiple-choice questions. At the end, output one line per question in exactly the "
             "form `Q<n>: <letter>` and nothing after those lines.\n"]
    for i, q in enumerate(qs, 1):
        opts = "\n".join(f"{LETTERS[j]}. {o}" for j, o in enumerate(q["options"]))
        parts.append(f"Q{i}. {q['question']}\n{opts}\n")
    return "\n".join(parts)


def mcq_score(final, qs):
    got = {int(n): l.upper() for n, l in re.findall(r"Q(\d+)\s*[:.)]\s*\(?([A-Ja-j])\b", final)}
    hits = [got.get(i) == q["answer"] for i, q in enumerate(qs, 1)]
    return sum(hits) / len(qs), {"got": got, "want": [q["answer"] for q in qs]}


def system_text(task, arm, cat=None):
    if arm == "none":
        return None
    if task == "mcq":
        return EXPERT_MCQ.format(cat=cat.split("#")[0]) if arm == "expert" else SCOPED_MCQ
    return EXPERT_CODE if arm == "expert" else SCOPED_CODE


def run(task, model, arm, rep, cat=None, tries=3):
    """Run one cell; retry when omp fell back to another model or a call errored (network blips happen)."""
    for attempt in range(tries):
        r = run_once(task, model, arm, rep, cat)
        if r["valid"]:
            break
    r["attempts"] = attempt + 1
    with open(f"{OUT}/results.jsonl", "a") as f:
        f.write(json.dumps(r) + "\n")
    return r


def run_once(task, model, arm, rep, cat=None):
    tag = f"{task}{'-' + cat.replace(' ', '_').replace('#', '_') if cat else ''}-{model}-{arm}-r{rep}"
    if task == "mcq":
        cwd = f"{OUT}/work/{tag}"; shutil.rmtree(cwd, ignore_errors=True); os.makedirs(cwd)
        qs = BATCHES[cat]; prompt = mcq_prompt(qs); tools = ["--no-tools"]
    else:
        cwd = f"{OUT}/work/{tag}"; shutil.rmtree(cwd, ignore_errors=True)
        shutil.copytree(os.path.join(base.FIX, task), cwd)
        prompt = base.PROMPTS[task]; tools = ["--tools", base.TOOLS[task]]
    sd = f"{OUT}/sessions/{tag}"; shutil.rmtree(sd, ignore_errors=True)
    cmd = ["omp", "-p", "--mode", "json", "--model", f"{MODELS[model]}:{EFFORT}", "--cwd", cwd,
           "--session-dir", sd, "--no-title", "--config", os.path.join(HERE, "omp-overlay.yml"), *tools]
    sysp = system_text(task, arm, cat)
    if sysp:
        cmd += ["--append-system-prompt", sysp]
    cmd.append(prompt)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        stdout, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        stdout, rc = (e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")), "timeout"
    wall = time.time() - t0
    turns = out = reason = 0; cost = 0.0; texts = []; seen = set(); errors = []
    for line in stdout.splitlines():
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get("message") or {}
        if d.get("type") == "message_end" and m.get("role") == "assistant":
            turns += 1; seen.add(f"{m.get('provider')}/{m.get('model')}")
            if m.get("stopReason") == "error":
                errors.append((m.get("errorMessage") or "")[:200])
            u = m.get("usage") or {}
            out += u.get("output") or 0; reason += u.get("reasoningTokens") or 0
            cost += (u.get("cost") or {}).get("total") or 0
            txt = "".join(c.get("text", "") for c in m.get("content") or []
                          if isinstance(c, dict) and c.get("type") == "text")
            if txt:
                texts.append(txt)
    # Grade every assistant text, not just the last one: a run can end with a short follow-up message
    # that refers back to an earlier full answer.
    final = "\n\n".join(texts)
    sc, detail = mcq_score(final, BATCHES[cat]) if task == "mcq" else base.score(task, final, cwd)
    r = dict(task=task, cat=cat, model=model, arm=arm, rep=rep, effort=EFFORT, rc=rc, wall=round(wall, 1),
             turns=turns, out=out, reasoning=reason, cost=round(cost, 5), score=round(sc, 3), detail=detail,
             model_seen=sorted(seen), errors=errors, final=final[-8000:])
    # Valid only if every assistant message came from the requested model and none errored.
    r["valid"] = rc == 0 and seen == {MODELS[model]} and not errors
    return r


def jobs():
    for rep in range(int(os.environ.get("REP_START", "0")), REPS):
        for task in TASKS:
            cats = sorted(BATCHES) if task == "mcq" else [None]
            for cat in cats:
                for arm in ARMS:
                    for model in MODELS:
                        yield (task, model, arm, rep, cat)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    js = list(jobs())
    if os.environ.get("LIMIT"):
        js = js[: int(os.environ["LIMIT"])]
    print(f"{len(js)} runs -> {OUT}/results.jsonl", flush=True)
    with cf.ThreadPoolExecutor(int(os.environ.get("PAR", "6"))) as ex:
        for r in ex.map(lambda a: run(*a), js):
            print(r["task"], r["cat"], r["model"], r["arm"], r["rep"], r["rc"], r["wall"], r["out"],
                  r["score"], r["model_seen"], flush=True)
