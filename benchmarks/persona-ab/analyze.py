#!/usr/bin/env python3
"""Summarise persona A/B results: score, time, tokens and cost per model x arm x task, plus paired tests.

Usage: python3 analyze.py [results.jsonl]
MCQ is compared per question (70 questions x reps, paired by question and rep) with an exact
two-sided sign test on discordant pairs (McNemar). Coding tasks have too few runs for a test; means only.
"""
import json, math, statistics as st, sys, collections, os

HERE = os.path.dirname(os.path.abspath(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "results-2026-11-14.jsonl")
rows = [json.loads(l) for l in open(path)]
valid = [r for r in rows if r.get("valid")]
print(f"runs: {len(rows)}  valid: {len(valid)}  invalid: {len(rows) - len(valid)}  "
      f"retried: {sum(1 for r in rows if r.get('attempts', 1) > 1)}")
for r in rows:
    if not r.get("valid"):
        print("  INVALID", r["task"], r.get("cat"), r["model"], r["arm"], r["rep"], r["model_seen"], r["errors"][:1])

ARMS = ["none", "expert", "scoped"]
models = sorted({r["model"] for r in valid})


def fmt(x, d=3):
    return "-" if x is None else f"{x:.{d}f}"


print("\n== Mean score by task (fraction correct) ==")
tasks = ["mcq", "hard", "bughunt", "fix"]
print("model  task     " + "  ".join(f"{a:>12}" for a in ARMS))
for m in models:
    for t in tasks:
        cells = []
        for a in ARMS:
            s = [r["score"] for r in valid if r["model"] == m and r["task"] == t and r["arm"] == a]
            cells.append(f"{fmt(st.mean(s)) if s else '-':>7} (n={len(s)})")
        print(f"{m:6} {t:8} " + "  ".join(cells))

print("\n== Cost / time / output tokens per run (all tasks) ==")
for m in models:
    for t in ["mcq", "coding"]:
        for a in ARMS:
            s = [r for r in valid if r["model"] == m and r["arm"] == a and ((r["task"] == "mcq") == (t == "mcq"))]
            if not s:
                continue
            print(f"{m:6} {t:7} {a:7} n={len(s):3}  median wall {st.median(r['wall'] for r in s):6.1f}s  "
                  f"mean out {st.mean(r['out'] for r in s):7.0f}  mean cost ${st.mean(r['cost'] for r in s):.4f}  "
                  f"total ${sum(r['cost'] for r in s):.2f}")
print(f"\nTotal spend (valid runs): " + ", ".join(f"{m} ${sum(r['cost'] for r in valid if r['model']==m):.2f}" for m in models))
print(f"Total spend (all attempts recorded): ${sum(r['cost'] for r in rows):.2f}")


def per_question(m, a):
    out = {}
    for r in valid:
        if r["model"] == m and r["task"] == "mcq" and r["arm"] == a:
            got, want = r["detail"]["got"], r["detail"]["want"]
            for i, w in enumerate(want, 1):
                out[(r["cat"], i, r["rep"])] = got.get(str(i)) == w
    return out


def sign_test(b, c):
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)


print("\n== MCQ paired comparison vs control (per question x rep) ==")
for m in models:
    base = per_question(m, "none")
    for a in ["expert", "scoped"]:
        other = per_question(m, a)
        keys = base.keys() & other.keys()
        if not keys:
            continue
        b = sum(1 for k in keys if base[k] and not other[k])   # control right, arm wrong
        c = sum(1 for k in keys if other[k] and not base[k])   # arm right, control wrong
        acc0 = sum(base[k] for k in keys) / len(keys); acc1 = sum(other[k] for k in keys) / len(keys)
        print(f"{m:6} {a:7} n={len(keys)}  control {acc0:.3f} -> {acc1:.3f} ({(acc1-acc0)*100:+.1f} pp)  "
              f"lost {b} / gained {c}  sign-test p={sign_test(b, c):.3f}")

print("\n== Coding: planted-defect hit rate per defect ==")
for m in models:
    for t in ["hard", "bughunt"]:
        for a in ARMS:
            s = [r["detail"] for r in valid if r["model"] == m and r["task"] == t and r["arm"] == a]
            if s:
                keys = sorted(s[0])
                print(f"{m:6} {t:8} {a:7} " + " ".join(f"{k}:{sum(d[k] for d in s)}/{len(s)}" for k in keys))
