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
            "SLACK_REVIEW_GH_LOGIN", "JIRA_URL", "JIRA_EMAIL", "JIRA_TOKEN")
with open(Path(__file__).resolve().parent / "fixtures_review_intent.json") as _f:
    FX = json.load(_f)  # anonymised real digest blocks: review asks and look-alikes


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
               "SLACK_REVIEW_TICKET_RE": TICKET_RE}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        for k in ENV_KEYS:
            if k not in env:
                os.environ.pop(k, None)
        rs._gh_login.cache_clear()


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


def pr_json(state="OPEN", decision="", reviews=(), commits=("2025-11-28T17:02:02Z",)):
    return json.dumps({
        "state": state, "reviewDecision": decision,
        "reviews": [{"author": {"login": a}, "state": "COMMENTED", "submittedAt": s}
                    for a, s in reviews],
        "commits": [{"committedDate": c, "oid": "x"} for c in commits]})


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
                "state,reviewDecision,reviews,commits"])

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
        now = 100000.0
        rs.save_state(self.state, {"ABC-1": {"session": "a", "at": now - 86401},
                                   "ABC-2": {"session": "b", "at": now - 10}})
        self.assertEqual(stat.S_IMODE(os.stat(self.state).st_mode), 0o600)
        self.assertEqual(rs.load_state(self.state, now),
                         {"ABC-2": {"session": "b", "at": now - 10}})

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
            os.kill(int(f.read()), 0)  # still alive
        overlay = os.path.join(self.dir, "omp-noresume.yml")
        self.assertEqual(self.argv(), ["-p", "--mode", "json", "--config", overlay,
                                       "--model", "m1", "--thinking", "high",
                                       "--cwd", self.tmp, "@" + self.brief()])
        with open(self.brief()) as f:
            self.assertIn(B1, f.read())

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
        self.calls = []

    def spawner(self, block, targets, now):
        self.calls.append(targets)
        return f"S{len(self.calls)}"

    def run_(self, text=SAMPLE, **kw):
        kw.setdefault("now", 100000.0)
        kw.setdefault("spawner", self.spawner)
        kw.setdefault("checker", lambda t: None)
        return rs.process(text, **kw)


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
        st = rs.load_state(self.state, 100000.0)
        self.assertEqual(st["ABC-401"], {"session": "S1", "at": 100000.0})
        self.assertEqual(st["ABC-77"]["session"], "S2")

    def test_claude_resume_line(self):
        os.environ["SLACK_REVIEW_AGENT"] = "claude"
        self.assertIn("review: S1 (acme/api#812, ABC-401) -> cd ~/code && claude --resume S1",
                      self.run_())

    def test_custom_lines(self):
        os.environ.update(SLACK_REVIEW_AGENT="custom", SLACK_REVIEW_CMD="rev {brief}")
        out = self.run_(spawner=lambda b, t, n: "/tmp/r.log")
        self.assertIn("review: started (log /tmp/r.log)", out)
        out = self.run_(spawner=self.spawner)
        self.assertIn("review: already running (acme/api#812, ABC-401; log /tmp/r.log)", out)
        self.assertEqual(self.calls, [])

    def test_already_running(self):
        rs.save_state(self.state, {"ABC-401": {"session": "old", "at": 99000.0},
                                   "acme/api#812": {"session": "new", "at": 99500.0},
                                   "ABC-77": {"session": "x", "at": 1.0}})  # stale
        out = self.run_()
        self.assertIn("review: already running new (acme/api#812, ABC-401) -> "
                      "cd ~/code && omp --resume new", out)
        self.assertEqual(self.calls, [["ABC-77"]])

    def test_partial_fresh_respawns(self):
        rs.save_state(self.state, {"ABC-401": {"session": "old", "at": 99000.0}})
        self.run_()
        self.assertEqual(self.calls[0], ["acme/api#812", "ABC-401"])

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
