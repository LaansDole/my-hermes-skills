#!/usr/bin/env python3
"""omp benchmark v2: Haiku 5.5 vs GPT-6 Luna across tasks x effort levels.

Tasks
  bughunt  - read-only; find seeded bugs in orders.py (5 seeded + 1 subtle). Score = seeded bugs found.
  fix      - edit textutil.py until test_textutil.py passes (bash allowed). Score = tests passing / 7.
  explore  - read-only repo Q&A on auto-learn-for-me with a known answer. Score = facts correct / 3.
"""
import concurrent.futures as cf, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")
# Default outside the repo so omp does not pick up this repo's AGENTS.md when reviewing fixtures.
OUT = os.environ.get("OUT", os.path.join(tempfile.gettempdir(), "omp-bench"))
REPO = os.environ.get("REPO", os.path.abspath(os.path.join(HERE, "..", "..")))  # explore task runs against this repo
# Override with your own provider/model ids, e.g. HAIKU=anthropic/claude-haiku-5-5 LUNA=openai/gpt-6-luna
MODELS = {"haiku": os.environ.get("HAIKU", "anthropic/claude-haiku-5-5"), "luna": os.environ.get("LUNA", "commandcode/gpt-6-luna")}
EFFORTS = os.environ.get("EFFORTS", "medium,high,max").split(",")
REPS = int(os.environ.get("REPS", "2"))
TASKS = os.environ.get("TASKS", "hard,bughunt,fix,explore").split(",")

PROMPTS = {
    "bughunt": ("Read-only. Do not edit. Review orders.py in the current directory and list every real bug "
                "(correctness, security, data loss). For each: line number, one-line explanation, one-line fix. "
                "No style nits."),
    "fix": ("Make every test in test_textutil.py pass by editing textutil.py only (never edit the tests). "
            "Run `python3 -m unittest -q` to verify before you finish. Reply with a one-paragraph summary."),
    "hard": ("Read-only. Do not edit or run anything. Review cache.py and limiter.py in the current directory "
             "against README.md. List every real defect (correctness, concurrency, spec violations) with file:line, "
             "one-line explanation and one-line fix. No style nits."),
    "explore": ("Read-only. In this repo answer exactly, one line each: (1) which script builds docs/index.html; "
                "(2) the version number in skills/slack/slack-mention-watch/SKILL.md frontmatter; "
                "(3) the file that defines READ_METHODS and how many methods it lists."),
}
TOOLS = {"hard": "read,grep,glob", "bughunt": "read,grep,glob", "fix": "read,grep,glob,edit,write,bash", "explore": "read,grep,glob"}

BUG_PATTERNS = {
    "A": r"range\(1, ?pages\)|off[- ]by[- ]one|last page|skips? (the )?(final|last)|pages \+ ?1",
    "B": r"mutable default|tags=\[\]|default (list|argument)|shared (list|across calls)",
    "C": r"injection|parameteri[sz]|placeholder|email = \?",
    "D": r"float|round|decimal|truncat|precision|int\(.*\*\s*100",
    "E": r"swallow|re-?raise|returns? `?none|last exception|hid(es|ing) (the )?(error|failure)|exhausted",
}
HARD_PATTERNS = {
    "H1": r"deadlock|re-?entran|rlock|not reentrant|already (holds|held)|acquire.{0,40}twice|block(s|ed)? forever|hangs?",
    "H2": r"get\(\).{0,160}(without|outside|no|not).{0,20}lock|(unlocked|unsynchroni[sz]ed|race).{0,120}(get|del|_data)",
    "H3": r"<\s*limit.{0,200}(<=|limit\s*-\s*1|99|off[- ]by[- ]one|one (fewer|less))|off[- ]by[- ]one|only (allows|permits) 99|99 requests",
    "H4": r"(refresh|reset|extend|renew|bump|slid)\w*.{0,120}(ttl|expir|window)|(ttl|expir|window).{0,120}(refresh|reset|extend|renew|never expire|sliding)",
}
def explore_answers():
    """Expected explore answers, read from the repo at run time so they stay correct as it changes."""
    skill = open(os.path.join(REPO, "skills/slack/slack-mention-watch/SKILL.md")).read()
    version = re.search(r"^version:\s*(\S+)", skill, re.M).group(1)
    src = open(os.path.join(REPO, "skills/slack/slack-mention-watch/scripts/watch_mentions.py")).read()
    block = re.search(r"READ_METHODS = frozenset\(\{(.*?)\}\)", src, re.S).group(1)
    n = len(re.findall(r'"[\w.]+"', block))
    words = {8: "eight", 9: "nine", 10: "ten"}.get(n, str(n))
    return [r"generate_docs\.py", re.escape(version),
            rf"watch_mentions\.py.{{0,200}}\b{n}\b|\b{n}\b.{{0,200}}watch_mentions\.py|{words}"]


def workdir(task, tag):
    d = f"{OUT}/work/{tag}"
    shutil.rmtree(d, ignore_errors=True)
    if task == "bughunt":
        shutil.copytree(f"{FIX}/bughunt", d)
    elif task == "hard":
        shutil.copytree(f"{FIX}/hard", d)
    elif task == "fix":
        shutil.copytree(f"{FIX}/fix", d)
    else:
        return REPO
    return d


def score(task, final, cwd):
    t = final.lower()
    if task == "bughunt":
        hits = {b: bool(re.search(p, t)) for b, p in BUG_PATTERNS.items()}
        return sum(hits.values()) / 5, hits
    if task == "hard":
        hits = {b: bool(re.search(p, t, re.S)) for b, p in HARD_PATTERNS.items()}
        return sum(hits.values()) / 4, hits
    if task == "fix":
        p = subprocess.run([sys.executable, "-m", "unittest", "-v"], cwd=cwd, capture_output=True, text=True)
        ok = len(re.findall(r" \.\.\. ok", p.stderr))
        tests_untouched = open(f"{cwd}/test_textutil.py").read() == open(f"{FIX}/fix/test_textutil.py").read()
        return (ok / 7 if tests_untouched else 0.0), {"passed": ok, "tests_untouched": tests_untouched}
    hits = [bool(re.search(p, final, re.I | re.S)) for p in explore_answers()]
    return sum(hits) / 3, hits


def run(task, model, effort, rep):
    cfg = f"{MODELS[model]}:{effort}"
    tag = f"{task}-{model}-{effort}-r{rep}"
    cwd = workdir(task, tag)
    sd = f"{OUT}/sessions/{tag}"
    shutil.rmtree(sd, ignore_errors=True)
    t0 = time.time()
    try:
        p = subprocess.run(["omp", "-p", "--mode", "json", "--model", cfg, "--cwd", cwd, "--session-dir", sd,
                            "--no-title", "--tools", TOOLS[task], PROMPTS[task]],
                           capture_output=True, text=True, timeout=1200)
        stdout, rc = p.stdout, p.returncode
    except subprocess.TimeoutExpired as e:
        stdout, rc = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
    wall = time.time() - t0
    turns = out = inp = reason = 0; cost = 0.0; final = ""; model_seen = None
    for line in stdout.splitlines():
        try: d = json.loads(line)
        except Exception: continue
        m = d.get("message") or {}
        if d.get("type") == "message_end" and m.get("role") == "assistant":
            turns += 1; model_seen = f"{m.get('provider')}/{m.get('model')}"
            u = m.get("usage") or {}
            out += u.get("output") or 0; reason += u.get("reasoningTokens") or 0
            inp += (u.get("input") or 0) + (u.get("cacheRead") or 0) + (u.get("cacheWrite") or 0)
            cost += (u.get("cost") or {}).get("total") or 0
            txt = "".join(c.get("text", "") for c in m.get("content") or [] if isinstance(c, dict) and c.get("type") == "text")
            if txt: final = txt
    sc, detail = score(task, final, cwd)
    r = dict(task=task, model=model, effort=effort, rep=rep, cfg=cfg, rc=rc, wall=round(wall, 1), turns=turns,
             out=out, reasoning=reason, inp=inp, cost=round(cost, 5), score=round(sc, 3), detail=detail,
             model_seen=model_seen, final=final[:4000])
    with open(f"{OUT}/results.jsonl", "a") as f:
        f.write(json.dumps(r) + "\n")
    return r


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    jobs = [(t, m, e, r) for r in range(REPS) for t in TASKS for e in EFFORTS for m in MODELS]
    with cf.ThreadPoolExecutor(int(os.environ.get("PAR", "6"))) as ex:
        for r in ex.map(lambda a: run(*a), jobs):
            print(r["task"], r["model"], r["effort"], r["rep"], r["rc"], r["wall"], r["turns"], r["out"],
                  r["score"], r["model_seen"], flush=True)
