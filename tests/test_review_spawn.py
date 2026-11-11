#!/usr/bin/env python3
"""Tests for skills/slack/slack-mention-watch/scripts/review_spawn.py (no network, no real agents).

Run:  python3 -m unittest -v tests.test_review_spawn
"""

import base64
import importlib.util
import io
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "skills/slack/slack-mention-watch/scripts/review_spawn.py"
_spec = importlib.util.spec_from_file_location("review_spawn_under_test", SCRIPT)
rs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rs)

HEADER = "NEW MENTIONS: 2   (watched user: @sam)   now: Fri 2026-11-06 10:30 +07"
B1 = "\n".join([
    "### Mention 1 -- #dev -- from Bob at Fri 2026-11-06 10:20",
    "Permalink: https://x.slack.com/archives/C1/p123?thread_ts=1.2",
    "Mention: @sam can you review <https://github.com/acme/api/pull/812|#812> for ABC-401?",
    "Reacted: :eyes:",
    "Thread (3 messages):",
    "[Fri 11-06 10:18] Bob: ABC-400 is ready",
    "    continuation lines are indented 4 spaces",
])
B2 = "\n".join([
    "### Mention 2 -- #qa -- from Eve at Fri 2026-11-06 10:25",
    "Mention: @sam please take a look at ABC-77",
    "    second line",
    "(thread context unavailable: ratelimited)",
])
SAMPLE = HEADER + "\n\n" + B1 + "\n\n" + B2 + "\n"
TICKET_RE = r"\b[A-Z][A-Z0-9]+-\d+\b"
WORKDIR = os.path.expanduser("~/code")
SUCCESS_LINE = "review: S1 (acme/api#812, ABC-401) -> cd ~/code && omp --resume S1"
ENV_KEYS = ("SLACK_REVIEW_AGENT", "SLACK_REVIEW_WORKDIR", "SLACK_REVIEW_MODEL",
            "SLACK_REVIEW_EFFORT", "SLACK_REVIEW_CMD", "SLACK_REVIEW_MAX_SPAWNS",
            "SLACK_REVIEW_TICKET_RE", "SLACK_REVIEW_INSTRUCTIONS", "SLACK_REVIEW_ID_TIMEOUT",
            "SLACK_REVIEW_GH_LOGIN", "JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN",
            "SLACK_REVIEW_JEV", "SLACK_REVIEW_JEV_MIN", "TYPESAFE_API_KEY", "SLACK_REVIEW_DAYS")
with open(Path(__file__).resolve().parent / "fixtures_review_intent.json") as _f:
    FX = json.load(_f)  # anonymised real digest blocks: review asks and look-alikes
A, B = "a" * 40, "b" * 40  # PR head revs
PR812 = "acme/api#812"


def entry(sid, at, agent="omp", rev=None, pid=None, **kw):
    """A session-table entry as process() records it."""
    return dict({"session": sid, "agent": agent, "created": at, "last_run": at, "runs": 1,
                 "rev": rev, "pid": pid, "pending": []}, **kw)


def dead_pid():
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def rev_checker(rev, reasons=None):
    """Checker that reports `rev` as every PR's head commit, like check_target via gh."""
    def check(t):
        if "#" in t and rev:
            rs.HEAD_REVS[t] = rev
        return (reasons or {}).get(t)
    return check


class Env(unittest.TestCase):
    """Isolated env: tmp state/spawn dirs, no dotenv file, gh unreachable, omp + tickets on."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.state = os.path.join(self.tmp, "state.json")
        self.dir = os.path.join(self.tmp, "spawns")
        env = {"SLACK_REVIEW_STATE": self.state, "SLACK_REVIEW_DIR": self.dir,
               "HERMES_DOTENV": os.path.join(self.tmp, "no.env"),
               "SLACK_REVIEW_GH": "/nonexistent/gh",  # missing binary fails open
               "SLACK_REVIEW_AGENT": "omp", "SLACK_REVIEW_WORKDIR": WORKDIR,
               "SLACK_REVIEW_TICKET_RE": TICKET_RE,
               "SLACK_REVIEW_JEV_LOG": os.path.join(self.tmp, "jev.jsonl")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ENV_KEYS:
            if k not in env:
                os.environ.pop(k, None)
        rs._gh_login.cache_clear()
        rs.LAUNCHED.clear()


# Parsing --------------------------------------------------------------------

class ParseTest(unittest.TestCase):
    def test_roundtrip_sample(self):
        header, blocks = rs.parse(SAMPLE)
        self.assertEqual(header, HEADER)
        self.assertEqual(blocks, [B1, B2 + "\n"])
        self.assertEqual(rs.assemble(header, blocks), SAMPLE)

    def test_no_blocks(self):
        t = '{"wakeAgent": false}\n'
        self.assertEqual(rs.parse(t), (t, []))
        self.assertEqual(rs.assemble(*rs.parse(t)), t)

    def test_empty_message_line_stays_in_block(self):
        b = B1 + "\n[Fri 11-06 10:19] Bob: para one\n    \n    para two"
        t = HEADER + "\n\n" + b + "\n\n" + B2
        header, blocks = rs.parse(t)
        self.assertEqual(blocks, [b, B2])
        self.assertEqual(rs.assemble(header, blocks), t)


class TargetsTest(Env):
    def test_sample(self):
        self.assertEqual(rs.targets(B1), ["acme/api#812", "ABC-401", "ABC-400"])
        self.assertEqual(rs.targets(B2), ["ABC-77"])

    def test_ticket_regex_off_by_default(self):
        os.environ.pop("SLACK_REVIEW_TICKET_RE")
        self.assertEqual(rs.targets(B1), ["acme/api#812"])
        self.assertEqual(rs.targets(B2), [])

    def test_dupes_suffix_and_ignored(self):
        b = ("ABC-1 ABC-1 https://GitHub.com/a/b.c/pull/9/files "
             "https://github.com/a/b.c/pull/9 https://github.com/a/b/issues/3 "
             "https://github.com/a/b ABC- abc-5")
        self.assertEqual(rs.targets(b), ["ABC-1", "a/b.c#9"])

    def test_max_five(self):
        b = " ".join(f"ABC-{i}" for i in range(8))
        self.assertEqual(rs.targets(b), [f"ABC-{i}" for i in range(5)])


class EligibleTest(Env):
    def test_rules(self):
        self.assertTrue(rs.eligible(B1))
        self.assertTrue(rs.eligible(B2))  # no Reacted line
        for r in (":eyes: (dry run, not sent)", "failed (ratelimited)"):
            self.assertTrue(rs.eligible(B1.replace(":eyes:", r)), r)
        for r in ("none (already replied)", "none (already reacted)", ":raised_hands:",
                  ":raised_hands: (dry run, not sent)", ":memo:", ":memo: (dry run, not sent)"):
            self.assertFalse(rs.eligible(B1.replace(":eyes:", r)), r)
        self.assertFalse(rs.eligible("### Mention 1 -- x\nMention: hi\nReacted: :eyes:"))


class IntentTest(Env):
    POS = ("can you review <https://github.com/o/r/pull/1|#1>?", "PTAL", "ptal when free",
           "pls re-review, I pushed fixes", "please review the auth change",
           "Hi, help me to review this", "could you take a look at ABC-1",
           "have a quick look when free", "Could you verify it on staging?",
           "would you approve this", "review this PR when you can", "re-review the fix pls",
           "<https://github.com/o/r/pull/1> ?", "<https://github.com/o/r/pull/9> check pls",
           "Hi could you help to review the hotfix?", "Could you review this one ?",
           "Can you check this?", "could you test it on staging", "can you check on staging",
           "could you verify the fix", "can you test the build pls", "can you check the PRs",
           "please check the pull request", "Could you review it so I can merge?")
    NEG = ("Review to move:\n◦ To dev → In dev",
           "Could you update the list based on what we discussed @sam",
           "Could you edit message to include today’s tickets in the section What i do: @sam",
           "could you edit your message", "can you edit the message?",
           "I reviewed with comment", "it is in review", "No need ticket for “Admin sidebar” @sam",
           "What are the items should be done today?", "thanks for abc-77",
           "Review items in the doc before standup",
           "deploy tomorrow, what items? <https://example.atlassian.net/browse/ABC-1|x>",
           "<https://github.com/o/r/pull/3> merged, see "
           "<https://x.slack.com/archives/C1/p1?thread_ts=1.2|thread>",
           "@sam There are many tickets in review, I’ve commented in some of them. Can you "
           "check and assign the remaining ones so I can review?",
           "Can you check and assign them?", "could you test and deploy it",
           "Could you assign ABC-1 so I can review?", "can you move it, then we will review",
           "pls move the tickets in review", "Could you assign ABC-2 so that I'll review it",
           "would you approve ABC-3")  # approve needs an object word, a bare key is not one

    def block(self, mention):
        """The thread asks for a review too: only the Mention text may count."""
        return ("### Mention 1 -- #x -- from B at T\nMention: " + mention.replace("\n", "\n    ")
                + "\nReacted: :eyes:\nThread (2 messages):\n[T] B: could you review ABC-9 pls"
                + "\n[T] B: " + mention.split("\n")[0])

    def test_phrases_mention_only(self):
        for m in self.POS:
            self.assertTrue(rs.review_intent(self.block(m)), m)
        for m in self.NEG:
            self.assertFalse(rs.review_intent(self.block(m)), m)

    def test_fixture(self):
        for name, b in FX["negatives"].items():
            self.assertIsNone(rs.review_intent(b), name)
        for name, p in FX["positives"].items():
            self.assertTrue(rs.review_intent(p["block"]), name)
            self.assertEqual(rs.scoped_targets(p["block"]), p["targets"], name)

    def test_scoped_targets(self):
        self.assertEqual(rs.scoped_targets(B1), ["acme/api#812", "ABC-401"])  # not ABC-400
        self.assertEqual(rs.scoped_targets(B2), ["ABC-77"])
        root = ("### M\nMention: could you review this?\nReacted: :eyes:\nThread (3 messages):\n"
                "[T] Bob: root\n    links ABC-5\n[T] Bob: ABC-6 too\n[T] Eve: could you review this?")
        self.assertEqual(rs.scoped_targets(root), ["ABC-5"])  # root continuation counts
        self.assertEqual(rs.scoped_targets(root.replace("links ABC-5", "no key")), [])


# Target checks --------------------------------------------------------------

def fake_bin(tmp, name, out, rc=0):
    """Executable that records argv to <tmp>/<name>-argv and prints `out`."""
    data = os.path.join(tmp, name + ".out")
    with open(data, "w") as f:
        f.write(out)
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + f'printf "%s\\n" "$@" >> "{tmp}/{name}-argv"\n'
                + f'if [ "$1" = api ]; then echo Sam; exit 0; fi\ncat "{data}"\nexit {rc}\n')
    os.chmod(path, 0o755)
    return path


def pr_json(state="OPEN", decision="", reviews=(), commits=("2025-11-28T17:02:02Z",), oid=None):
    return json.dumps({
        "state": state, "reviewDecision": decision,
        "reviews": [{"author": {"login": a}, "state": "COMMENTED", "submittedAt": s}
                    for a, s in reviews],
        "commits": [{"committedDate": c, "oid": "x"} for c in commits], "headRefOid": oid})


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class CheckTargetTest(Env):
    PR = "acme/web#471"

    def gh(self, out, rc=0):
        os.environ["SLACK_REVIEW_GH"] = fake_bin(self.tmp, "gh", out, rc)

    def test_gh_state_and_decision(self):
        os.environ["SLACK_REVIEW_GH_LOGIN"] = "sam"
        for out, want in ((pr_json("MERGED", "APPROVED"), "merged"),
                          (pr_json("CLOSED"), "closed"),
                          (pr_json(decision="APPROVED"), "approved"),
                          (pr_json(decision="REVIEW_REQUIRED"), None)):
            self.gh(out)
            self.assertEqual(rs.check_target(self.PR), want, out)
        with open(os.path.join(self.tmp, "gh-argv")) as f:
            self.assertEqual(f.read().split("\n")[:7], [
                "pr", "view", "471", "-R", "acme/web", "--json",
                "state,reviewDecision,reviews,commits,headRefOid"])

    def test_head_rev_remembered(self):
        rs.HEAD_REVS.clear()
        self.gh(pr_json(oid=B))
        self.assertIsNone(rs.check_target(self.PR))
        self.assertEqual(rs.HEAD_REVS, {self.PR: B})
        self.gh(pr_json("MERGED", oid=A))
        self.assertEqual(rs.check_target(self.PR), "merged")
        self.assertEqual(rs.HEAD_REVS, {self.PR: A})

    def test_reviewed_by_you(self):
        os.environ["SLACK_REVIEW_GH_LOGIN"] = "sam"
        commits = ("2025-11-28T10:00:00Z", "2025-11-28T17:02:02Z")
        for reviews, want in (
                ([("sam", "2025-11-28T17:02:02Z")], "already reviewed by you"),
                ([("Sam", "2025-11-29T01:00:00Z")], "already reviewed by you"),
                ([("sam", "2025-11-28T17:02:01Z")], None),  # before last commit
                ([("bob", "2025-11-29T01:00:00Z")], None),
                ([("sam", None)], None)):  # pending review
            self.gh(pr_json(reviews=reviews, commits=commits))
            self.assertEqual(rs.check_target(self.PR), want, reviews)

    def test_login_from_gh_api(self):
        self.gh(pr_json(reviews=[("sam", "2025-11-29T01:00:00Z")]))
        self.assertEqual(rs.check_target(self.PR), "already reviewed by you")
        with open(os.path.join(self.tmp, "gh-argv")) as f:
            self.assertIn("api\nuser\n--jq\n.login\n", f.read())

    def test_gh_fail_open(self):
        os.environ["SLACK_REVIEW_GH_LOGIN"] = "sam"
        self.assertIsNone(rs.check_target(self.PR))  # missing binary
        for out, rc in ((pr_json("MERGED"), 1), ("not json", 0), ("[1]", 0), ("{}", 0)):
            self.gh(out, rc)
            self.assertIsNone(rs.check_target(self.PR), out)

    def test_ticket_without_jira_creds_not_checked(self):
        with mock.patch("urllib.request.urlopen") as u:
            self.assertIsNone(rs.check_target("ABC-402"))
        u.assert_not_called()

    def test_jira(self):
        os.environ.update(JIRA_URL="https://jira.example.com/", JIRA_EMAIL="me@example.com",
                          JIRA_TOKEN="tok")

        def st(name, key):
            return json.dumps({"fields": {"status": {"name": name,
                                                     "statusCategory": {"key": key}}}}).encode()
        reqs = []
        for body, want in ((st("Done", "done"), "done (Done)"),
                           (st("In Dev", "indeterminate"), None),
                           (b"<html>", None), (b'{"fields": null}', None), (None, None)):
            def fake(req, timeout=None, body=body):
                reqs.append(req)
                if body is None:
                    raise OSError("offline")
                return FakeResp(body)
            with mock.patch("urllib.request.urlopen", fake):
                self.assertEqual(rs.check_target("ABC-402"), want, body)
        req = reqs[0]
        self.assertEqual(req.full_url,
                         "https://jira.example.com/rest/api/2/issue/ABC-402?fields=status")
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.get_header("Authorization"),
                         "Basic " + base64.b64encode(b"me@example.com:tok").decode())


# Annotation and state -------------------------------------------------------

class AnnotateTest(unittest.TestCase):
    def test_after_reacted(self):
        out = rs.annotate(B1, "X").split("\n")
        self.assertEqual(out[3:5], ["Reacted: :eyes:", "X"])

    def test_after_mention_continuations(self):
        out = rs.annotate(B2 + "\n", "X")
        self.assertEqual(out, "\n".join([
            "### Mention 2 -- #qa -- from Eve at Fri 2026-11-06 10:25",
            "Mention: @sam please take a look at ABC-77",
            "    second line",
            "X",
            "(thread context unavailable: ratelimited)",
        ]) + "\n")

    def test_mention_last_line(self):
        self.assertEqual(rs.annotate("### M\nMention: a\n    b\n", "X"),
                         "### M\nMention: a\n    b\nX\n")


class StateTest(Env):
    def test_missing_and_corrupt(self):
        self.assertEqual(rs.load_state(self.state, 1000), {})
        with open(self.state, "w") as f:
            f.write("{nope")
        self.assertEqual(rs.load_state(self.state, 1000), {})

    def test_save_prune_mode(self):
        now = 100 * 86400.0
        rs.save_state(self.state, {"ABC-1": entry("a", now - 31 * 86400),
                                   "ABC-2": entry("b", now - 29 * 86400, rev=A)})
        self.assertEqual(stat.S_IMODE(os.stat(self.state).st_mode), 0o600)
        self.assertEqual(rs.load_state(self.state, now),
                         {"ABC-2": entry("b", now - 29 * 86400, rev=A)})

    def test_migrates_old_shape(self):
        now = 100000.0
        with open(self.state, "w") as f:  # pre-2.7: {target: {session, at}}, 24 h dedupe
            json.dump({"ABC-1": {"session": "a", "at": now - 90000.0}, "ABC-2": 3,
                       "ABC-3": {"at": 1.0}, "ABC-4": {"session": "", "at": now}}, f)
        self.assertEqual(rs.load_state(self.state, now),
                         {"ABC-1": entry("a", now - 90000.0, agent=None)})
        with open(self.state, "w") as f:
            f.write("[1]")
        self.assertEqual(rs.load_state(self.state, now), {})

    def test_default_path(self):
        os.environ.pop("SLACK_REVIEW_STATE")
        self.assertEqual(rs.state_path(),
                         os.path.expanduser("~/.hermes/scripts/.slack-review-spawn.json"))

    def test_dotenv_config(self):
        os.environ.pop("SLACK_REVIEW_STATE")
        with open(os.environ["HERMES_DOTENV"], "w") as f:
            f.write("SLACK_REVIEW_STATE=/tmp/x.json\n")
        self.assertEqual(rs.state_path(), "/tmp/x.json")


# Brief ----------------------------------------------------------------------

class BriefTest(Env):
    def test_contents(self):
        b = rs.build_brief(B1, ["acme/api#812", "ABC-401"])
        for s in (B1, "acme/api#812", "ABC-401", "READ ONLY", "P0", "P1", "No P0/P1 findings",
                  "gh pr diff", "gh pr checks", "git fetch", "NEVER edit", "push", "approve",
                  "Never post to Slack", "file:line"):
            self.assertIn(s, b)
        self.assertNotIn("Additional instructions", b)

    def test_instructions_appended(self):
        path = os.path.join(self.tmp, "rules.md")
        with open(path, "w") as f:
            f.write("Check migrations twice.\n")
        os.environ["SLACK_REVIEW_INSTRUCTIONS"] = path
        b = rs.build_brief(B1, ["acme/api#812"])
        self.assertIn("## Additional instructions\n\nCheck migrations twice.", b)
        self.assertGreater(b.index("Check migrations"), b.index("No P0/P1 findings"))

    def test_followup(self):
        b = rs.build_followup(["acme/api#812", "ABC-1"], [B1, B2], [("acme/api#812", A, B)])
        for s in (B1, B2, f"git diff {A}..{B}", "git fetch origin pull/812/head", "ABC-1",
                  "resumed", "READ ONLY", "No P0/P1 findings", "NEVER edit", "push",
                  "Never post to Slack"):
            self.assertIn(s, b)
        self.assertLess(b.index(B1), b.index(B2))
        b = rs.build_followup(["acme/api#812"], [B1], [("acme/api#812", A, None)])
        self.assertIn("gh pr diff 812 -R acme/api", b)


# Spawn ----------------------------------------------------------------------

def fake_agent(tmp, name, body):
    """Fake agent binary on PATH: records argv (one per line) and its pid."""
    path = os.path.join(tmp, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + f'printf "%s\\n" "$@" > "{tmp}/argv"\n'
                + f'pwd > "{tmp}/cwd"\necho $$ > "{tmp}/pid"\n' + textwrap.dedent(body))
    os.chmod(path, 0o755)
    os.environ["PATH"] = tmp + os.pathsep + os.environ.get("PATH", "")
    return path


class SpawnTest(Env):
    def setUp(self):
        super().setUp()
        os.environ["SLACK_REVIEW_WORKDIR"] = self.tmp
        self.addCleanup(self.kill_fake)

    def kill_fake(self):
        try:
            with open(os.path.join(self.tmp, "pid")) as f:
                os.killpg(int(f.read()), signal.SIGKILL)
        except (OSError, ValueError):
            pass

    def argv(self):
        with open(os.path.join(self.tmp, "argv")) as f:
            return f.read().split("\n")[:-1]

    def brief(self):
        names = [n for n in os.listdir(self.dir) if n.endswith(".md")]
        self.assertEqual(len(names), 1)
        return os.path.join(self.dir, names[0])

    def test_omp_success(self):
        fake_agent(self.tmp, "omp", """echo '{"type":"session","id":"sess-1"}'\nsleep 5\n""")
        os.environ.update(SLACK_REVIEW_MODEL="m1", SLACK_REVIEW_EFFORT="high")
        t0 = time.time()
        self.assertEqual(rs.spawn(B1, ["acme/api#812", "ABC-401"], t0), "sess-1")
        self.assertLess(time.time() - t0, 2)
        with open(os.path.join(self.tmp, "pid")) as f:
            pid = int(f.read())
        os.kill(pid, 0)  # still alive
        self.assertEqual(rs.LAUNCHED, {"sess-1": pid})  # process() records it for the busy guard
        overlay = os.path.join(self.dir, "omp-noresume.yml")
        self.assertEqual(self.argv(), ["-p", "--mode", "json", "--config", overlay,
                                       "--model", "m1", "--thinking", "high",
                                       "--cwd", self.tmp, "@" + self.brief()])
        with open(self.brief()) as f:
            self.assertIn(B1, f.read())

    def test_omp_resume_keeps_sid(self):
        fake_agent(self.tmp, "omp", "sleep 5\n")  # no session line before the timeout
        os.environ.update(SLACK_REVIEW_ID_TIMEOUT="1", SLACK_REVIEW_MODEL="m1")
        self.assertEqual(rs.resume("R0", "follow-up text", [PR812], time.time()), "R0")
        self.assertTrue(self.brief().endswith("-acme-api-812-followup.md"), self.brief())
        with open(self.brief()) as f:
            self.assertEqual(f.read(), "follow-up text")
        self.assertEqual(self.argv(), [
            "-p", "--mode", "json", "--resume", "R0", "--config",
            os.path.join(self.dir, "omp-noresume.yml"), "--model", "m1", "--cwd", self.tmp,
            "@" + self.brief()])
        self.assertIn("R0", rs.LAUNCHED)

    def test_claude_resume(self):
        os.environ["SLACK_REVIEW_AGENT"] = "claude"
        fake_agent(self.tmp, "claude",
                   """echo '{"type":"system","subtype":"init","session_id":"c-1"}'\n""")
        self.assertEqual(rs.resume("c-1", "follow-up text", ["ABC-1"], time.time()), "c-1")
        argv = self.argv()
        self.assertEqual(argv[:6], ["-p", "follow-up text", "--resume", "c-1",
                                    "--output-format", "stream-json"])
        self.assertEqual(argv[argv.index("--permission-mode"):][:2],
                         ["--permission-mode", "default"])
        self.assertIn("--allowedTools", argv)

    def test_omp_no_model_no_effort(self):
        fake_agent(self.tmp, "omp", """echo '{"type":"session","id":"sess-1"}'\n""")
        rs.spawn(B1, ["ABC-401"], time.time())
        self.assertNotIn("--model", self.argv())
        self.assertNotIn("--thinking", self.argv())

    def test_noresume_overlay_rewritten(self):
        os.makedirs(self.dir)
        overlay = os.path.join(self.dir, "omp-noresume.yml")
        with open(overlay, "w") as f:
            f.write("autoResume: true\n")
        fake_agent(self.tmp, "omp", """echo '{"type":"session","id":"sess-1"}'\n""")
        rs.spawn(B1, ["ABC-401"], time.time())
        with open(overlay) as f:
            self.assertEqual(f.read(), "autoResume: false\n")

    def test_claude_success(self):
        os.environ.update(SLACK_REVIEW_AGENT="claude", SLACK_REVIEW_MODEL="m2",
                          SLACK_REVIEW_EFFORT="high")  # effort is omp only
        fake_agent(self.tmp, "claude", """\
            echo '{"type":"system","subtype":"hook","session_id":"nope"}'
            echo '{"type":"system","subtype":"init","session_id":"c-1"}'
            sleep 5
            """)
        self.assertEqual(rs.spawn(B1, ["acme/api#812"], time.time()), "c-1")
        with open(self.brief()) as f:
            brief = f.read()
        argv = self.argv()
        self.assertEqual(argv[:2], ["-p", brief.split("\n")[0]])  # prompt right after -p
        rest = argv[argv.index("--output-format"):]
        self.assertEqual(rest, [
            "--output-format", "stream-json", "--verbose", "--model", "m2",
            "--permission-mode", "default", "--allowedTools", "Read", "Grep", "Glob",
            "Bash(gh pr view:*)", "Bash(gh pr diff:*)", "Bash(gh pr checks:*)",
            "Bash(gh api:*)", "Bash(git fetch:*)", "Bash(git show:*)", "Bash(git diff:*)",
            "Bash(git log:*)", "--disallowedTools", "Edit", "Write", "NotebookEdit"])
        self.assertEqual("\n".join(argv[1:argv.index("--output-format")]), brief)
        with open(os.path.join(self.tmp, "cwd")) as f:
            self.assertEqual(os.path.realpath(f.read().strip()), os.path.realpath(self.tmp))

    def test_custom_returns_log(self):
        os.environ.update(SLACK_REVIEW_AGENT="custom",
                          SLACK_REVIEW_CMD=f"{self.tmp}/rev --brief {{brief}} --in '{{workdir}}'")
        fake_agent(self.tmp, "rev", "echo hello\n")
        log = rs.spawn(B1, ["acme/api#812"], time.time())
        self.assertTrue(log.startswith(self.dir) and log.endswith(".log"), log)
        deadline = time.time() + 3  # custom returns at once; let the fake write its argv
        while not os.path.exists(os.path.join(self.tmp, "cwd")) and time.time() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.argv(), ["--brief", self.brief(), "--in", self.tmp])

    def test_exit_early(self):
        fake_agent(self.tmp, "omp", "echo boom >&2\nexit 1\n")
        with self.assertRaises(rs.SpawnError) as cm:
            rs.spawn(B1, ["ABC-401"], time.time())
        self.assertIn("exited 1", str(cm.exception))
        self.assertIn("boom", str(cm.exception))
        self.assertTrue(cm.exception.log.endswith(".err"))

    def test_timeout(self):
        fake_agent(self.tmp, "omp", "sleep 5\n")
        os.environ["SLACK_REVIEW_ID_TIMEOUT"] = "1"
        t0 = time.time()
        with self.assertRaises(rs.SpawnError) as cm:
            rs.spawn(B1, ["ABC-401"], t0)
        self.assertLess(time.time() - t0, 3)
        self.assertTrue(cm.exception.log.endswith(".jsonl"))

    def test_missing_binary(self):
        os.environ.update(SLACK_REVIEW_AGENT="custom", SLACK_REVIEW_CMD="/nonexistent/rev {brief}")
        with self.assertRaises(rs.SpawnError) as cm:
            rs.spawn(B1, ["ABC-401"], time.time())
        self.assertIn("cannot start", str(cm.exception))


# Orchestration --------------------------------------------------------------

def digest(*blocks, header=HEADER):
    return header + "\n\n" + "\n\n".join(b.rstrip("\n") for b in blocks) + "\n"


def mblock(mention, n=1, reacted=":eyes:"):
    return "\n".join([f"### Mention {n} -- #dev -- from Bob at Fri 2026-11-06 10:2{n}",
                      f"Mention: {mention}", f"Reacted: {reacted}"])


class ProcBase(Env):
    def setUp(self):
        super().setUp()
        self.calls, self.resumes = [], []

    def spawner(self, block, targets, now):
        self.calls.append(targets)
        return f"S{len(self.calls)}"

    def resumer(self, sid, brief, targets, now):
        self.resumes.append((sid, targets, brief))
        return sid

    def run_(self, text=SAMPLE, **kw):
        kw.setdefault("now", 100000.0)
        kw.setdefault("spawner", self.spawner)
        kw.setdefault("resumer", self.resumer)
        kw.setdefault("checker", lambda t: None)
        return rs.process(text, **kw)

    def seed(self, table):
        rs.save_state(self.state, table)

    def table(self, now=100000.0):
        return rs.load_state(self.state, now)


class ProcessTest(ProcBase):
    def test_feature_off_identical(self):
        os.environ.pop("SLACK_REVIEW_AGENT")
        self.assertIs(self.run_(), SAMPLE)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(self.state))

    def test_bad_config_raises(self):
        os.environ["SLACK_REVIEW_AGENT"] = "vim"
        with self.assertRaises(ValueError):
            self.run_()
        os.environ["SLACK_REVIEW_AGENT"] = "omp"
        os.environ.pop("SLACK_REVIEW_WORKDIR")
        with self.assertRaises(ValueError):
            self.run_()
        os.environ.update(SLACK_REVIEW_AGENT="custom", SLACK_REVIEW_WORKDIR=WORKDIR)
        with self.assertRaises(ValueError):  # no SLACK_REVIEW_CMD
            self.run_()

    def test_mixed_skip(self):
        checked = []

        def checker(t):
            checked.append(t)
            return {"acme/api#812": "merged", "ABC-77": "done (Done)"}.get(t)
        b3 = B1.replace(":eyes:", ":memo:").replace("Mention 1", "Mention 3")
        out = self.run_(SAMPLE.rstrip("\n") + "\n\n" + b3 + "\n", checker=checker)
        header, blocks = rs.parse(out)
        self.assertEqual(blocks[0], rs.annotate(B1, (
            "review: S1 (ABC-401) -> cd ~/code && omp --resume S1"
            " [skipped: acme/api#812 merged]")))
        self.assertEqual(blocks[1], rs.annotate(B2, "review: skipped (ABC-77 done (Done))"))
        self.assertEqual(blocks[2], b3 + "\n")  # ineligible: untouched, not checked
        self.assertEqual(checked, ["acme/api#812", "ABC-401", "ABC-77"])
        self.assertEqual(self.calls, [["ABC-401"]])
        self.assertEqual(set(rs.load_state(self.state, 100000.0)), {"ABC-401"})

    def test_all_skipped(self):
        out = self.run_(checker=lambda t: "closed" if "#" in t else "done (Done)")
        self.assertIn("review: skipped (acme/api#812 closed; ABC-401 done (Done))", out)
        self.assertEqual(self.calls, [])
        self.assertEqual(rs.load_state(self.state, 100000.0), {})

    def test_dry_run_checks(self):
        out = self.run_(dry_run=True, checker=lambda t: "merged" if "#" in t else None)
        self.assertIn("review: (dry run, would spawn for: ABC-401) "
                      "[skipped: acme/api#812 merged]", out)
        self.assertFalse(os.path.exists(self.state))

    def test_spawn_and_record(self):
        out = self.run_()
        header, blocks = rs.parse(out)
        self.assertEqual(header, HEADER)
        self.assertEqual(blocks[0], rs.annotate(B1, SUCCESS_LINE))
        self.assertEqual(blocks[1], rs.annotate(
            B2 + "\n", "review: S2 (ABC-77) -> cd ~/code && omp --resume S2"))
        st = self.table()
        self.assertEqual(st, {PR812: entry("S1", 100000.0), "ABC-401": entry("S1", 100000.0),
                              "ABC-77": entry("S2", 100000.0)})

    def test_claude_resume_line(self):
        os.environ["SLACK_REVIEW_AGENT"] = "claude"
        self.assertIn("review: S1 (acme/api#812, ABC-401) -> cd ~/code && claude --resume S1",
                      self.run_())

    def test_custom_lines(self):
        os.environ.update(SLACK_REVIEW_AGENT="custom", SLACK_REVIEW_CMD="rev {brief}")
        out = self.run_(spawner=lambda b, t, n: "/tmp/r.log")
        self.assertIn("review: started (log /tmp/r.log)", out)
        self.assertEqual(self.table()["ABC-401"], entry("/tmp/r.log", 100000.0, agent="custom"))
        out = self.run_(spawner=self.spawner)
        self.assertIn("review: skipped (acme/api#812 already reviewed /tmp/r.log; "
                      "ABC-401 already reviewed /tmp/r.log)", out)
        self.assertEqual(self.calls, [])

    def test_old_state_migrated(self):
        with open(self.state, "w") as f:  # pre-2.7 shape
            json.dump({"ABC-401": {"session": "old", "at": 99000.0}}, f)
        out = self.run_(digest(B1))
        self.assertIn("review: S1 (acme/api#812) -> cd ~/code && omp --resume S1 "
                      "[skipped: ABC-401 already reviewed old]", out)
        with open(self.state) as f:
            self.assertEqual(json.load(f)["ABC-401"], entry("old", 99000.0, agent=None))

    def test_dry_run(self):
        out = self.run_(dry_run=True)
        self.assertIn("review: (dry run, would spawn for: acme/api#812, ABC-401)", out)
        self.assertEqual(self.calls, [])
        self.assertFalse(os.path.exists(self.state))

    def test_cap(self):
        os.environ["SLACK_REVIEW_MAX_SPAWNS"] = "1"
        out = self.run_()
        self.assertIn(SUCCESS_LINE, out)
        self.assertIn("review: skipped (spawn cap reached)", out)
        self.assertEqual(len(self.calls), 1)

    def test_failed(self):
        def bad(block, targets, now):
            raise rs.SpawnError("x" * 300, "/tmp/l.err")
        out = self.run_(spawner=bad)
        self.assertIn("review: failed (" + "x" * 200 + "; log /tmp/l.err)", out)
        self.assertEqual(rs.load_state(self.state, 100000.0), {})

    def test_already_replied_and_no_blocks_untouched(self):
        t = HEADER + "\n\n" + B1.replace(":eyes:", "none (already replied)") + "\n"
        self.assertEqual(self.run_(t), t)
        self.assertEqual(self.run_('{"wakeAgent": false}\n'), '{"wakeAgent": false}\n')
        self.assertEqual(self.calls, [])


RESUME = "cd ~/code && omp --resume"
P812 = "### Mention 1 -- #dev -- from Bob at T\nMention: PTAL https://github.com/acme/api/pull/812"
B1_813 = B1.replace("812", "813").replace("Mention 1", "Mention 2")


class SessionTest(ProcBase):
    def test_reviewed_targets_filtered_per_target(self):
        self.seed({"ABC-401": entry("R0", 99000.0)})
        out = self.run_(digest(B1))
        self.assertEqual((self.calls, self.resumes), ([[PR812]], []))
        self.assertIn(f"review: S1 ({PR812}) -> {RESUME} S1 [skipped: ABC-401 already reviewed R0]",
                      out)
        self.assertEqual(self.table(), {"ABC-401": entry("R0", 99000.0),
                                        PR812: entry("S1", 100000.0)})

    def test_pr_same_rev_skipped_at_any_age(self):
        self.seed({PR812: entry("R0", 1000.0, rev=A)})
        out = self.run_(digest(P812), checker=rev_checker(A))
        self.assertIn(f"review: skipped ({PR812} already reviewed R0)", out)
        self.assertEqual((self.calls, self.resumes), ([], []))

    def test_pr_new_rev_resumes_same_session(self):
        self.seed({PR812: entry("R0", 99000.0, rev=A)})
        out = self.run_(digest(P812), checker=rev_checker(B))
        self.assertIn(f"review: resumed R0 ({PR812}, aaaaaaa..bbbbbbb) -> {RESUME} R0", out)
        self.assertEqual(self.calls, [])
        (sid, tgts, brief), = self.resumes
        self.assertEqual((sid, tgts), ("R0", [PR812]))
        for s in (f"git diff {A}..{B}", P812, "NEVER edit", "Never post to Slack"):
            self.assertIn(s, brief)
        self.assertEqual(self.table()[PR812],
                         entry("R0", 99000.0, rev=B, last_run=100000.0, runs=2))

    def test_unknown_rev_and_tickets_use_days(self):
        self.seed({PR812: entry("R0", 99000.0, rev=A), "ABC-5": entry("T0", 99000.0)})
        pr, ticket = digest(P812), digest(mblock("could you review ABC-5?"))
        for t in (pr, ticket):  # gh failed (head unknown) / ticket: reviewed 1000 s ago
            self.assertIn("already reviewed", self.run_(t))
        later = 99000.0 + 8 * 86400  # past SLACK_REVIEW_DAYS (7)
        self.assertIn(f"review: resumed R0 ({PR812}, aaaaaaa..?) -> {RESUME} R0",
                      self.run_(pr, now=later))
        self.assertIn(f"review: resumed T0 (ABC-5) -> {RESUME} T0", self.run_(ticket, now=later))
        os.environ["SLACK_REVIEW_DAYS"] = "0.001"  # 86 s
        self.assertIn("review: resumed T0", self.run_(ticket, now=later + 100))
        self.assertEqual([r[0] for r in self.resumes], ["R0", "T0", "T0"])
        self.assertEqual(self.table(later + 100)["ABC-5"]["runs"], 3)

    def test_new_and_resumed_targets_split(self):
        now = 10 * 86400.0
        self.seed({"ABC-401": entry("R0", now - 8 * 86400)})
        out = self.run_(digest(B1), now=now)
        self.assertIn(f"\nreview: S1 ({PR812}) -> {RESUME} S1\n"
                      f"review: resumed R0 (ABC-401) -> {RESUME} R0\n", out)
        self.assertEqual((self.calls, [r[1] for r in self.resumes]), ([[PR812]], [["ABC-401"]]))

    def test_other_agent_session_gets_a_new_run(self):
        now = 10 * 86400.0
        self.seed({"ABC-401": entry("C0", now - 8 * 86400, agent="claude"),
                   PR812: entry("M0", now - 8 * 86400, agent=None)})  # migrated: agent unknown
        self.run_(digest(B1), now=now)
        self.assertEqual((self.calls, self.resumes), ([[PR812, "ABC-401"]], []))
        self.assertEqual(self.table(now)["ABC-401"], entry("S1", now))

    def test_custom_always_new_run_no_busy_guard(self):
        os.environ.update(SLACK_REVIEW_AGENT="custom", SLACK_REVIEW_CMD="rev {brief}")
        now = 10 * 86400.0
        self.seed({"ABC-401": entry("/old.log", now - 8 * 86400, agent="custom",
                                    pid=os.getpid())})
        out = self.run_(digest(B1), now=now)
        self.assertIn("review: started (log S1)", out)
        self.assertEqual((self.calls, self.resumes), ([[PR812, "ABC-401"]], []))

    def test_busy_queues_then_next_tick_resumes(self):
        self.seed({PR812: entry("R0", 99000.0, rev=A, pid=os.getpid())})  # still running
        out = self.run_(digest(P812), checker=rev_checker(B))
        self.assertIn("review: busy R0 (update queued)", out)
        self.assertEqual(self.resumes, [])
        st = self.table()
        self.assertEqual(st[PR812]["pending"], [P812])
        st[PR812]["pid"] = dead_pid()
        self.seed(st)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):  # a tick without new mentions drains the queue
            out = self.run_('{"wakeAgent": false}\n', now=100100.0, checker=rev_checker(B))
        self.assertEqual(out, '{"wakeAgent": false}\n')
        self.assertEqual(err.getvalue(), f"[slack-review] queued update: review: resumed R0 "
                                         f"({PR812}, aaaaaaa..bbbbbbb) -> {RESUME} R0\n")
        (sid, tgts, brief), = self.resumes
        self.assertEqual((sid, tgts), ("R0", [PR812]))
        self.assertIn(P812, brief)
        self.assertIn(f"git diff {A}..{B}", brief)
        e = self.table(100100.0)[PR812]
        self.assertEqual((e["pending"], e["runs"], e["rev"], e["last_run"]), ([], 2, B, 100100.0))

    def test_queued_update_joins_the_next_resume(self):
        q = P812.replace("PTAL", "PTAL, pushed fixes")
        self.seed({PR812: entry("R0", 1000.0, rev=A, pid=dead_pid(), pending=[q]),
                   "ABC-5": entry("R0", 1000.0, pid=dead_pid())})
        now = 10 * 86400.0  # both last ran > SLACK_REVIEW_DAYS ago
        self.run_(digest(mblock("could you review ABC-5?")), now=now)
        (sid, tgts, brief), = self.resumes  # one resume for both targets of R0
        self.assertEqual((sid, tgts), ("R0", ["ABC-5", PR812]))
        self.assertLess(brief.index(q), brief.index("could you review ABC-5?"))
        self.assertEqual([e["pending"] for e in self.table(now).values()], [[], []])

    def test_queued_update_dropped_when_no_review_needed(self):
        self.seed({PR812: entry("R0", 1000.0, rev=A, pid=dead_pid(), pending=[P812])})
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.run_(digest(B2), checker=lambda t: "merged" if "#" in t else None)
        self.assertEqual(err.getvalue(), "[slack-review] queued update: review: dropped queued "
                                         f"update for R0 ({PR812}: no review needed)\n")
        self.assertEqual(self.resumes, [])
        self.assertEqual(self.table()[PR812]["pending"], [])

    def test_cap_counts_resumes(self):
        os.environ["SLACK_REVIEW_MAX_SPAWNS"] = "1"
        self.seed({PR812: entry("R0", 1000.0, rev=A)})
        out = self.run_(digest(P812, B1_813), checker=rev_checker(B))
        self.assertEqual((len(self.resumes), self.calls), (1, []))
        self.assertIn("review: skipped (spawn cap reached)", out)

    def test_dry_run_resume_writes_nothing(self):
        self.seed({PR812: entry("R0", 1000.0, rev=A)})
        out = self.run_(digest(P812, B1_813), dry_run=True, checker=rev_checker(B))
        self.assertIn(f"review: (dry run, would resume R0 for: {PR812})", out)
        self.assertIn("review: (dry run, would spawn for: acme/api#813, ABC-401)", out)
        self.assertEqual((self.calls, self.resumes), ([], []))
        self.assertEqual(self.table(), {PR812: entry("R0", 1000.0, rev=A)})

    def test_failed_resume_keeps_entry(self):
        def bad(*a):
            raise rs.SpawnError("gone", "/tmp/l.err")
        self.seed({PR812: entry("R0", 1000.0, rev=A)})
        out = self.run_(digest(P812), checker=rev_checker(B), resumer=bad)
        self.assertIn("review: failed (gone; log /tmp/l.err)", out)
        self.assertEqual(self.table(), {PR812: entry("R0", 1000.0, rev=A)})

    def test_launch_pid_recorded(self):
        def spawner(block, targets, now):
            rs.LAUNCHED["S9"] = 4242
            return "S9"
        self.run_(digest(P812), spawner=spawner)
        self.assertEqual(self.table()[PR812]["pid"], 4242)
        self.assertEqual(rs.LAUNCHED, {})



class IntentProcessTest(ProcBase):
    def test_real_negatives_skipped(self):
        for name, b in FX["negatives"].items():
            out = self.run_(digest(b, header=FX["header"]))
            self.assertEqual(rs.parse(out)[1][0], rs.annotate(
                b + "\n", "review: skipped (not a review request)"), name)
        self.assertEqual(self.calls, [])
        self.assertEqual(rs.load_state(self.state, 100000.0), {})

    def test_positives_spawn_scoped_targets(self):
        for p in FX["positives"].values():
            self.run_(digest(p["block"], header=FX["header"]))
        self.assertEqual(self.calls, [p["targets"] for p in FX["positives"].values()])

    def test_intent_without_scoped_target(self):
        b = (mblock("@sam could you review this?")
             + "\nThread (2 messages):\n[T] Bob: hello\n[T] Eve: ABC-5 maybe")
        out = self.run_(digest(b))
        self.assertIn("review: skipped (no target in mention or thread root)", out)
        self.assertEqual(self.calls, [])

    def test_no_target_anywhere_untouched(self):
        t = digest(mblock("@sam could you review this?"))
        self.assertEqual(self.run_(t), t)


class FakeJev:
    """urlopen stand-in: each answer is an exception or p(review)."""

    def __init__(self, *answers):
        self.answers, self.reqs = list(answers), []

    def __call__(self, req, timeout=None):
        self.reqs.append((req, timeout))
        a = self.answers.pop(0)
        if isinstance(a, BaseException):
            raise a
        return FakeResp(json.dumps({"answers": {"review": {"noul": a}},
                                    "model": "jev-1"}).encode())


class JevTest(ProcBase):
    def setUp(self):
        super().setUp()
        os.environ.update(SLACK_REVIEW_JEV="1", TYPESAFE_API_KEY="tk-secret")
        self.log = os.environ["SLACK_REVIEW_JEV_LOG"]

    def jev(self, *answers):
        fake = FakeJev(*answers)
        p = mock.patch("urllib.request.urlopen", fake)
        p.start()
        self.addCleanup(p.stop)
        return fake

    def rows(self):
        with open(self.log) as f:
            return [json.loads(line) for line in f]

    def test_low_p_skips_and_request_shape(self):
        fake = self.jev(0.29)
        out = self.run_(digest(B1))
        self.assertIn("review: skipped (not a review request (jev 0.29))", out)
        self.assertEqual(self.calls, [])
        (req, timeout), = fake.reqs
        self.assertEqual((req.full_url, req.get_method(), timeout),
                         ("https://api.typesafe.ai/v1/systemone", "POST", 15))
        self.assertEqual(req.get_header("Authorization"), "Bearer tk-secret")
        body = json.loads(req.data)
        self.assertEqual(body["model"], "jev-latest")
        self.assertEqual(body["state"], {
            "watched_user": "@sam",
            "mention": "@sam can you review #812 https://github.com/acme/api/pull/812 for ABC-401?",
            "thread": ["[Fri 11-06 10:18] Bob: ABC-400 is ready\n"
                       "continuation lines are indented 4 spaces"]})
        self.assertEqual(list(body["questions"]), ["review"])
        self.assertEqual(body["questions"]["review"]["type"], "noul")
        self.assertIn("not edit their own message", body["questions"]["review"]["instructions"])
        row, = self.rows()
        self.assertEqual(stat.S_IMODE(os.stat(self.log).st_mode), 0o600)
        self.assertEqual((row["p_review"], row["decision"], row["model"], row["error"]),
                         (0.29, "skip", "jev-1", None))
        self.assertEqual(row["permalink"], "https://x.slack.com/archives/C1/p123?thread_ts=1.2")
        self.assertTrue(row["regex"])
        for k in ("logged_at", "mention", "ms"):
            self.assertIn(k, row)
        with open(self.log) as f:
            self.assertNotIn("tk-secret", f.read())

    def test_high_p_reviews(self):
        self.jev(0.93)
        self.run_(digest(B1))
        self.assertEqual(self.calls, [["acme/api#812", "ABC-401"]])
        self.assertEqual(self.rows()[0]["decision"], "review")

    def test_min_env(self):
        os.environ["SLACK_REVIEW_JEV_MIN"] = "0.95"
        self.jev(0.93)
        self.assertIn("(not a review request (jev 0.93))", self.run_(digest(B1)))

    def test_default_min_is_0_8(self):
        self.jev(0.68, 0.8)  # 0.68: a triage ask that passed the old regex; real asks ~0.98
        self.assertIn("(not a review request (jev 0.68))", self.run_(digest(B1)))
        self.assertEqual(self.calls, [])
        self.run_(digest(B1))
        self.assertEqual(len(self.calls), 1)

    def test_error_falls_back_to_regex(self):
        # the exception text may echo the request header: only its type name is logged
        self.jev(urllib.error.URLError("down"), ValueError("Bearer tk-secret leaked"))
        self.run_(digest(B1, B1_813))
        self.assertEqual(len(self.calls), 2)
        rows = self.rows()
        self.assertEqual([(r["p_review"], r["decision"], r["error"]) for r in rows],
                         [(None, "review", "URLError"), (None, "review", "ValueError")])
        with open(self.log) as f:
            self.assertNotIn("tk-secret", f.read())

    def test_bad_p_is_an_error(self):
        self.jev(float("nan"), 1.5)
        self.run_(digest(B1, B1_813))
        self.assertEqual(len(self.calls), 2)  # regex alone
        self.assertEqual([r["error"] for r in self.rows()], ["ValueError", "ValueError"])

    def test_401_disables_for_tick(self):
        fake = self.jev(urllib.error.HTTPError("u", 401, "no", {}, None), 0.01)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            self.run_(digest(B1, B1_813))
        self.assertEqual(len(fake.reqs), 1)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(err.getvalue(), "[slack-review] jev: auth rejected (HTTP 401)\n")
        self.assertEqual(self.rows()[0]["error"], "HTTPError 401")
        self.run_(digest(B1_813.replace("813", "814")))  # next tick asks Jev again
        self.assertEqual(len(fake.reqs), 2)

    def test_no_call_when_off_keyless_or_regex_negative(self):
        fake = self.jev()
        os.environ.pop("SLACK_REVIEW_JEV")  # off by default
        self.run_(digest(B1))
        os.environ["SLACK_REVIEW_JEV"] = "1"
        os.environ.pop("TYPESAFE_API_KEY")
        self.run_(digest(B1_813))
        os.environ["TYPESAFE_API_KEY"] = "tk-secret"
        self.run_(digest(FX["negatives"]["update_list"]))
        self.assertEqual(fake.reqs, [])
        self.assertEqual(len(self.calls), 2)
        self.assertFalse(os.path.exists(self.log))

    def test_key_from_dotenv(self):
        os.environ.pop("TYPESAFE_API_KEY")
        with open(os.environ["HERMES_DOTENV"], "w") as f:
            f.write("OTHER=1\nTYPESAFE_API_KEY='tk-file'\n")
        fake = self.jev(0.9)
        self.run_(digest(B1))
        self.assertEqual(fake.reqs[0][0].get_header("Authorization"), "Bearer tk-file")

    def test_dry_run_logs_to_stderr(self):
        self.jev(0.9)
        err = io.StringIO()
        with mock.patch("sys.stderr", err):
            out = self.run_(digest(B1), dry_run=True)
        self.assertIn("would spawn for", out)
        self.assertFalse(os.path.exists(self.log))
        tag, line = err.getvalue().split(" ", 1)
        self.assertEqual((tag, json.loads(line)["p_review"]), ("[slack-review]", 0.9))


# CLI wrapper ----------------------------------------------------------------

FAKE_WATCH = """\
import os, sys
def env(name):
    return os.environ.get(name)
if __name__ == "__main__":
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "args"), "w") as f:
        f.write(" ".join(sys.argv[1:]))
    sys.stdout.write(%r)
    sys.exit(3)
"""


class WrapperTest(Env):
    def run_main(self, *args, output=SAMPLE):
        d = os.path.join(self.tmp, "scripts")
        os.makedirs(d)
        shutil.copy(SCRIPT, d)
        with open(os.path.join(d, "watch_mentions.py"), "w") as f:
            f.write(FAKE_WATCH % output)
        r = subprocess.run([sys.executable, os.path.join(d, "review_spawn.py"), *args],
                           env=dict(os.environ, PATH="/nonexistent"),
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        with open(os.path.join(d, "args")) as f:
            r.child_args = f.read()
        return r

    def test_feature_off_byte_identical(self):
        os.environ.pop("SLACK_REVIEW_AGENT")
        r = self.run_main("--dry-run", output=SAMPLE.rstrip("\n"))
        self.assertEqual(r.stdout, SAMPLE.rstrip("\n"))
        self.assertEqual(r.returncode, 3)
        self.assertEqual(r.child_args, "--digest --react --dry-run")

    def test_dry_run_line(self):
        r = self.run_main("--dry-run")
        self.assertIn("review: (dry run, would spawn for: acme/api#812, ABC-401)", r.stdout)
        self.assertEqual(r.returncode, 3)
        self.assertFalse(os.path.exists(self.state))

    def test_error_falls_back_to_raw_digest(self):
        os.environ["SLACK_REVIEW_AGENT"] = "vim"
        r = self.run_main()
        self.assertEqual(r.stdout, SAMPLE)
        self.assertRegex(r.stderr, r"^\[slack-review\] error: ValueError: .*vim")
        self.assertEqual(r.returncode, 3)


if __name__ == "__main__":
    unittest.main()
