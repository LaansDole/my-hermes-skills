#!/usr/bin/env python3
"""Tests for skills/slack/slack-mention-watch/scripts/dashboard.py (no network, no real hermes).

Run:  python3 -m unittest -v tests.test_dashboard
"""

import hashlib
import http.client
import importlib.util
import json
import os
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "skills/slack/slack-mention-watch/scripts/dashboard.py"
_spec = importlib.util.spec_from_file_location("dashboard_under_test", SCRIPT)
dash = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dash)

DIGEST, ALERTS, EXTRA = "aaa111", "bbb222", "ccc333"
P1 = "https://x.slack.com/archives/C1/p111?thread_ts=1.2"
P2 = "https://x.slack.com/archives/C2/p222"
P3 = "https://x.slack.com/archives/C3/p333"
INTRO = ("## Script Output\nThe following data was collected by a pre-run script. "
         "Use it as context for your analysis.\n\n```\n")
PROMPT = "\n```\n\nYou receive new Slack @mentions of the user.\n### Mention 9 -- not a block\n"
OUT1 = "\n".join([
    "NEW MENTIONS: 2   (watched user: @sam)   now: Fri 2026-11-06 10:30 +07",
    "",
    "### Mention 1 -- #dev -- from Bob at Fri 2026-11-06 10:20",
    f"Permalink: {P1}",
    "Mention: @sam can you review <https://github.com/acme/api/pull/812|#812>?",
    "    second line",
    "Reacted: :eyes:",
    "review: S1 (acme/api#812) -> cd ~/code && omp --resume S1",
    "Thread (2 messages):",
    "[Fri 11-06 10:18] Bob: the fix is ready",
    "[Fri 11-06 10:20] Bob: @sam can you review it?",
    "",
    "### Mention 2 -- DM -- from Eve at Fri 2026-11-06 10:25",
    f"Permalink: {P2}",
    "Mention: @sam thanks for the help",
    "(thread context unavailable: ratelimited)",
])
OUT2 = "\n".join([
    "NEW MENTIONS: 1   (watched user: @sam)   now: Fri 2026-11-06 09:30 +07",
    "",
    "### Mention 1 -- #dev -- from Bob at Fri 2026-11-06 10:20",
    f"Permalink: {P1}",
    "Mention: duplicate of the first one",
])
OUT_OLD = "\n".join([
    "NEW MENTIONS: 1   (watched user: @sam)   now: Mon 2026-10-26 09:30 +07",
    "",
    "### Mention 1 -- #old -- from Dan at Mon 2026-10-26 09:00",
    f"Permalink: {P3}",
    "Mention: ancient ping",
])


def job(id, name, script=None, **kw):
    return dict({"id": id, "name": name, "script": script, "enabled": True, "state": "scheduled",
                 "no_agent": False, "schedule": {"kind": "interval", "minutes": 5,
                                                 "display": "every 5m"},
                 "schedule_display": "every 5m", "next_run_at": "2026-11-22T10:05:00+07:00",
                 "last_run_at": "2026-11-22T10:00:00+07:00", "last_status": "ok",
                 "last_error": None, "paused_at": None}, **kw)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "hermes-home"
        (self.home / "cron").mkdir(parents=True)
        (self.home / "scripts").mkdir()
        self.log = Path(self.tmp.name) / "hermes.log"
        self.bin = self.fake_hermes("ok", 0)
        env = mock.patch.dict(os.environ, {
            "HERMES_HOME": str(self.home), "HERMES_BIN": str(self.bin),
            "HERMES_DOTENV": str(self.home / ".env"),
            "SLACK_REVIEW_STATE": str(self.home / "scripts" / "review.json")})
        env.start()
        self.addCleanup(env.stop)
        self.now = time.time()
        self.write_jobs()
        self.write_dbs()

    def fake_hermes(self, name, code):
        p = Path(self.tmp.name) / f"hermes-{name}"
        p.write_text("#!/usr/bin/env python3\nimport json, sys\n"
                     f"open({str(self.log)!r}, 'a').write(json.dumps(sys.argv[1:]) + '\\n')\n"
                     + ("" if code == 0 else "sys.stderr.write('boom: job is locked\\n')\n")
                     + f"sys.exit({code})\n")
        p.chmod(0o755)
        return p

    def calls(self):
        return [json.loads(l) for l in self.log.read_text().splitlines()] if self.log.exists() else []

    def write_jobs(self):
        s = self.home / "scripts"
        (s / "resume_alerts.sh").write_text(f"#!/bin/bash\nhermes cron resume {ALERTS}\n")
        (s / "off.sh").write_text(f"hermes cron resume {DIGEST}\n")
        (s / "near.sh").write_text(f"hermes cron resume {DIGEST}2 x{DIGEST} {DIGEST}_b\n")
        self.jobs = [
            job(DIGEST, "slack-mention-digest", "slack_mention_digest_cron.py", model="m-1"),
            job(ALERTS, "my-alerts", "/abs/path/slack_mention_watch_cron.py", enabled=False,
                state="paused", paused_at="2026-11-22T09:00:00+07:00", no_agent=True),
            job(EXTRA, "slack-mention-extra"),
            job("hhh999", "resume-my-alerts", "resume_alerts.sh", no_agent=True,
                next_run_at="2026-11-25T08:00:00+07:00",
                schedule={"kind": "once", "display": "once at 2026-11-25 08:00"}),
            job("off000", "resume-off", "off.sh", no_agent=True, enabled=False),
            job("near00", "resume-near", "near.sh", no_agent=True),
            job("gone00", "resume-gone", "missing.sh", no_agent=True),
            job("zzz000", "daily-report", "report.py"),
        ]
        (self.home / "cron" / "jobs.json").write_text(json.dumps({"jobs": self.jobs}))

    def write_dbs(self):
        c = sqlite3.connect(self.home / "state.db")
        c.execute("CREATE TABLE sessions(id TEXT, source TEXT, title TEXT, model TEXT,"
                  " started_at REAL, message_count INTEGER)")
        c.execute("CREATE TABLE messages(id INTEGER PRIMARY KEY, session_id TEXT, role TEXT,"
                  " content TEXT, timestamp REAL)")
        t = "slack-mention-digest \u00b7 Nov 06 10:30"
        n = self.now
        sessions = [("s1", "cron", t, "m-1", n - 3600, 2), ("s2", "cron", t, "m-1", n - 7200, 2),
                    ("gate", "cron", t, "m-1", n - 60, 0),
                    ("other", "cron", "slack-mention-digest-other \u00b7 Nov 06", "m-1", n - 50, 2),
                    ("cli", "cli", t, "m-1", n - 40, 2),
                    ("old", "cron", t, "m-0", n - 10 * 86400, 2)]
        c.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?)", sessions)
        msgs = [("s1", "user", INTRO + OUT1 + PROMPT), ("s1", "assistant", ""),
                ("s1", "assistant", "REVIEW\n- Bob asks for a review of #812 <b>now</b>"),
                ("s2", "user", INTRO + OUT2 + PROMPT), ("s2", "assistant", " [SILENT]\n"),
                ("gate", "user", INTRO + OUT1 + PROMPT),
                ("other", "user", INTRO + OUT1 + PROMPT), ("other", "assistant", "other job"),
                ("cli", "user", INTRO + OUT1 + PROMPT), ("cli", "assistant", "typed by hand"),
                ("old", "user", INTRO + OUT_OLD + PROMPT), ("old", "assistant", "NO ACTION old")]
        c.executemany("INSERT INTO messages(session_id, role, content, timestamp) VALUES (?,?,?,?)",
                      [(*m, n + i) for i, m in enumerate(msgs)])
        c.commit()
        c.close()
        c = sqlite3.connect(self.home / "cron" / "executions.db")
        c.execute("CREATE TABLE executions(id TEXT, job_id TEXT, status TEXT, claimed_at TEXT,"
                  " started_at TEXT, finished_at TEXT, error TEXT, delivery_outcome TEXT)")
        rows = [("e1", DIGEST, "completed", "suppressed", None),
                ("e2", DIGEST, "completed", "delivered", None),
                ("e3", DIGEST, "failed", "delivered", "provider 403"),
                ("e4", DIGEST, "missed", None, None),
                ("e5", DIGEST, "unknown", None, "lost"),
                ("e6", DIGEST, "running", None, None),
                ("e7", DIGEST, "completed", "suppressed", None),
                ("x1", "zzz000", "failed", None, "not ours")]
        c.executemany("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?)",
                      [(i, j, s, f"2026-11-22T10:0{k}:00+07:00", None,
                        f"2026-11-22T10:0{k}:05+07:00", e, o)
                       for k, (i, j, s, o, e) in enumerate(rows)])
        c.commit()
        c.close()


class JobsTest(Base):
    def test_watched_detection(self):
        ids = lambda **kw: [j["id"] for j in dash.watched_jobs(dash.load_jobs(), **kw)]  # noqa: E731
        self.assertEqual(ids(), [DIGEST, ALERTS, EXTRA])
        self.assertEqual(ids(ids=["zzz000"]), ["zzz000"])
        self.assertEqual(ids(ids=["nope"]), [])

    def test_missing_or_corrupt_jobs_file(self):
        (self.home / "cron" / "jobs.json").write_text("{not json")
        self.assertEqual(dash.status()["jobs"], [])
        (self.home / "cron" / "jobs.json").unlink()
        self.assertEqual(dash.status()["jobs"], [])

    def test_helper_detection(self):
        by = {j["id"]: j for j in dash.status()["jobs"]}
        self.assertEqual(by[ALERTS]["scheduled_resume"],
                         {"job_id": "hhh999", "run_at": "2026-11-25T08:00:00+07:00"})
        # disabled helper, near-miss tokens and a helper whose script is gone do not count
        self.assertIsNone(by[DIGEST]["scheduled_resume"])
        self.assertIsNone(by[EXTRA]["scheduled_resume"])

    def test_status_shape(self):
        st = dash.status()
        self.assertEqual(sorted(st), ["jobs", "now"])
        datetime.fromisoformat(st["now"])
        j = st["jobs"][1]
        self.assertEqual({k: j[k] for k in ("id", "name", "enabled", "state", "schedule", "paused_at")},
                         {"id": ALERTS, "name": "my-alerts", "enabled": False, "state": "paused",
                          "schedule": "every 5m", "paused_at": "2026-11-22T09:00:00+07:00"})
        for k in ("next_run_at", "last_run_at", "last_status", "last_error", "scheduled_resume"):
            self.assertIn(k, j)


class RepliesTest(Base):
    def test_parse_mentions(self):
        ms = dash.parse_mentions(INTRO + OUT1 + PROMPT)
        self.assertEqual(ms, [
            {"channel": "#dev", "sender": "Bob", "at": "Fri 2026-11-06 10:20", "permalink": P1,
             "text": "@sam can you review <https://github.com/acme/api/pull/812|#812>?\nsecond line",
             "reacted": ":eyes:",
             "review": "S1 (acme/api#812) -> cd ~/code && omp --resume S1"},
            {"channel": "DM", "sender": "Eve", "at": "Fri 2026-11-06 10:25", "permalink": P2,
             "text": "@sam thanks for the help", "reacted": "", "review": ""}])
        self.assertEqual(dash.parse_mentions("no digest here\n### Mention 1 -- a -- from b at c"), [])
        self.assertEqual(dash.parse_mentions(None), [])

    def test_replies(self):
        r = dash.replies(DIGEST)
        self.assertEqual(r["total"], 3)
        self.assertEqual([i["session_id"] for i in r["items"]], ["s1", "s2", "old"])  # newest first
        s1, s2, _ = r["items"]
        self.assertEqual((s1["silent"], s1["model"], s1["reply"]),
                         (False, "m-1", "REVIEW\n- Bob asks for a review of #812 <b>now</b>"))
        self.assertEqual([m["permalink"] for m in s1["mentions"]], [P1, P2])
        self.assertAlmostEqual(datetime.fromisoformat(s1["started_at"]).timestamp(),
                               self.now - 3600, places=3)
        self.assertTrue(s2["silent"])

    def test_replies_filter_and_paging(self):
        self.assertEqual([i["session_id"] for i in dash.replies(DIGEST, q="BOB ASKS")["items"]], ["s1"])
        self.assertEqual([i["session_id"] for i in dash.replies(DIGEST, q="ancient")["items"]], ["old"])
        r = dash.replies(DIGEST, limit=1, offset=1)
        self.assertEqual((r["total"], [i["session_id"] for i in r["items"]]), (3, ["s2"]))
        self.assertEqual(dash.replies(EXTRA), {"items": [], "total": 0})
        with self.assertRaises(dash.BadRequest):
            dash.replies("zzz000")

    def test_mentions_window_and_dedupe(self):
        ms = dash.mentions(DIGEST, hours=24)["items"]
        self.assertEqual([(m["permalink"], m["session_id"]) for m in ms], [(P2, "s1"), (P1, "s1")])
        self.assertEqual(ms[1]["reacted"], ":eyes:")
        self.assertEqual(dash.mentions(DIGEST, hours=0.5)["items"], [])
        self.assertEqual([m["permalink"] for m in dash.mentions(DIGEST, hours=24 * 30)["items"]],
                         [P2, P1, P3])

    def test_missing_state_db(self):
        (self.home / "state.db").unlink()
        self.assertEqual(dash.replies(DIGEST), {"items": [], "total": 0})
        self.assertEqual(dash.mentions(DIGEST)["items"], [])
        self.assertFalse((self.home / "state.db").exists())  # a read-only open creates nothing


class ActivityTest(Base):
    def test_classification_and_counts(self):
        a = dash.activity(DIGEST)
        self.assertEqual(a["counts"], {"nothing_new": 2, "sent": 1, "error": 2, "missed": 1})
        self.assertEqual([(i["id"], i["outcome"]) for i in a["items"]], [
            ("e7", "nothing_new"), ("e6", "running"), ("e5", "error"), ("e4", "missed"),
            ("e3", "error"), ("e2", "sent"), ("e1", "nothing_new")])
        self.assertEqual(a["items"][4]["error"], "provider 403")
        self.assertEqual(sorted(a["items"][0]), ["claimed_at", "error", "finished_at", "id",
                                                 "outcome", "status"])
        self.assertEqual(len(dash.activity(DIGEST, limit=2)["items"]), 2)

    def test_missing_db(self):
        (self.home / "cron" / "executions.db").unlink()
        self.assertEqual(dash.activity(DIGEST)["items"], [])


class ReviewsTest(Base):
    def test_empty_state(self):
        r = dash.reviews()
        self.assertEqual(r["rows"], [])
        self.assertTrue(r["note"])

    def test_rows(self):
        Path(os.environ["SLACK_REVIEW_STATE"]).write_text(json.dumps({"acme/api#812": {
            "session": "R0", "agent": "omp", "created": self.now, "last_run": self.now,
            "runs": 2, "rev": "a" * 40, "pid": None, "pending": []}}))
        rows = dash.reviews()["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual({k: rows[0][k] for k in ("TARGET", "AGENT", "SESSION", "RUNS", "REV", "STATUS")},
                         {"TARGET": "acme/api#812", "AGENT": "omp", "SESSION": "R0", "RUNS": "2",
                          "REV": "aaaaaaa", "STATUS": "idle"})


class ControlTest(Base):
    def test_pause(self):
        r = dash.control(DIGEST, "pause")
        self.assertTrue(r["ok"])
        self.assertEqual(r["status"]["id"], DIGEST)
        self.assertEqual(self.calls(), [["cron", "pause", DIGEST]])

    def test_resume_removes_helper_first(self):
        self.assertTrue(dash.control(ALERTS, "resume")["ok"])
        self.assertEqual(self.calls(), [["cron", "remove", "hhh999"], ["cron", "resume", ALERTS]])

    def test_resume_without_helper(self):
        dash.control(DIGEST, "resume")
        self.assertEqual(self.calls(), [["cron", "resume", DIGEST]])

    def test_pause_until(self):
        until = (datetime.now() + timedelta(days=2)).replace(microsecond=0)
        r = dash.control(ALERTS, "pause_until", until.isoformat())
        self.assertTrue(r["ok"], r)
        iso = until.astimezone().isoformat()
        name = f"slack_dashboard_resume_{ALERTS}.sh"
        self.assertEqual(self.calls(), [
            ["cron", "pause", ALERTS], ["cron", "remove", "hhh999"],
            ["cron", "create", iso, "--name", "resume-my-alerts", "--script", name, "--no-agent",
             "--deliver", "local", "--catch-up", "on"]])
        helper = self.home / "scripts" / name
        self.assertEqual(stat.S_IMODE(helper.stat().st_mode), 0o700)
        body = helper.read_text()
        self.assertTrue(body.startswith("#!/bin/bash\n"))
        self.assertIn(f"{self.bin} cron resume {ALERTS}", body)
        self.assertIn("resumed my-alerts", body)
        self.assertIn("FAILED", body)
        self.assertIn(f"hermes cron resume {ALERTS}", body)

    def test_pause_until_accepts_an_offset(self):
        until = (datetime.now().astimezone() + timedelta(hours=3)).replace(microsecond=0)
        self.assertTrue(dash.control(DIGEST, "pause_until", until.isoformat())["ok"])
        self.assertEqual(self.calls()[-1][2], until.isoformat())

    def test_pause_until_rejects_bad_times(self):
        past = (datetime.now() - timedelta(minutes=1)).isoformat()
        for until in (past, "next tuesday", "", None, 5):
            with self.assertRaises(dash.BadRequest, msg=repr(until)):
                dash.control(DIGEST, "pause_until", until)
        self.assertEqual(self.calls(), [])
        self.assertEqual(list((self.home / "scripts").glob("slack_dashboard_resume_*")), [])

    def test_cancel_resume(self):
        self.assertTrue(dash.control(ALERTS, "cancel_resume")["ok"])
        self.assertEqual(self.calls(), [["cron", "remove", "hhh999"]])
        with self.assertRaises(dash.BadRequest):
            dash.control(DIGEST, "cancel_resume")

    def test_rejects_unknown_job_and_action(self):
        for j, a in (("zzz000", "pause"), ("hhh999", "resume"), ("nope", "pause"),
                     (DIGEST, "remove"), (DIGEST, ""), (None, "pause")):
            with self.assertRaises(dash.BadRequest, msg=(j, a)):
                dash.control(j, a)
        self.assertEqual(self.calls(), [])

    def test_shell_unsafe_job_fields(self):
        evil = "x; touch /tmp/pwned"
        self.jobs.append(job(evil, "slack-mention-evil"))
        self.jobs[0]["name"] = "slack-mention-digest'; rm -rf ~ #"
        (self.home / "cron" / "jobs.json").write_text(json.dumps({"jobs": self.jobs}))
        with self.assertRaises(dash.BadRequest):
            dash.control(evil, "pause_until", (datetime.now() + timedelta(days=1)).isoformat())
        dash.control(DIGEST, "pause_until", (datetime.now() + timedelta(days=1)).isoformat())
        body = (self.home / "scripts" / f"slack_dashboard_resume_{DIGEST}.sh").read_text()
        self.assertIn("'\"'\"'", body)  # the quote in the name is shell-escaped

    def test_failure_surfaces_stderr(self):
        with mock.patch.dict(os.environ, {"HERMES_BIN": str(self.fake_hermes("fail", 1))}):
            r = dash.control(DIGEST, "pause")
            self.assertEqual((r["ok"], r["status"]["id"]), (False, DIGEST))
            self.assertIn("boom: job is locked", r["message"])
            until = (datetime.now() + timedelta(days=1)).isoformat()
            self.assertFalse(dash.control(DIGEST, "pause_until", until)["ok"])
        # a failed pause stops the sequence: nothing is created
        self.assertEqual(self.calls(), [["cron", "pause", DIGEST]] * 2)

    def test_missing_binary(self):
        with mock.patch.dict(os.environ, {"HERMES_BIN": str(self.home / "no-such-hermes")}):
            r = dash.control(DIGEST, "pause")
        self.assertFalse(r["ok"])
        self.assertTrue(r["message"])


class LiveTest(Base):
    def test_runs_recent_and_returns_output(self):
        done = mock.Mock(stdout="No @sam mentions in the last 2 h.\n", stderr="", returncode=0)
        with mock.patch.object(dash.subprocess, "run", return_value=done) as run:
            self.assertEqual(dash.live("2"), {"output": done.stdout, "exit": 0})
        argv = run.call_args.args[0]
        self.assertEqual((os.path.basename(argv[1]), argv[2:]), ("watch_mentions.py", ["--recent", "2"]))
        self.assertEqual(run.call_args.kwargs["timeout"], 120)
        self.assertFalse(run.call_args.kwargs.get("shell"))
        for bad in ("abc", "-1", "0", "nan", "99999", "1; ls"):
            with self.assertRaises(dash.BadRequest, msg=bad):
                dash.live(bad)


class HttpTest(Base):
    def setUp(self):
        super().setUp()
        self.start()

    def start(self, job_ids=None):
        self.srv = dash.make_server(0, job_ids)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def req(self, method, path, body=None, **headers):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(c.close)
        data = None if body is None else json.dumps(body).encode()
        c.request(method, path, body=data, headers={k.replace("_", "-"): v for k, v in headers.items()})
        r = c.getresponse()
        raw = r.read().decode()
        return r.status, r.getheader("Content-Type"), raw

    def post(self, body, token=None, **headers):
        headers.setdefault("X_CSRF_Token", self.srv.token if token is None else token)
        return self.req("POST", "/api/control", body, **headers)

    def test_page_and_api(self):
        code, ctype, page = self.req("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn("text/html", ctype)
        self.assertIn(f'<meta name="csrf" content="{self.srv.token}">', page)
        self.assertNotRegex(page, r"(?i)max-width\s*:")  # full-width rule; media queries excepted
        self.assertNotRegex(page, r"(?i)(src|href)=[\"']?(https?:)?//")  # no external assets
        code, ctype, raw = self.req("GET", "/api/status")
        self.assertEqual((code, ctype), (200, "application/json"))
        self.assertEqual([j["id"] for j in json.loads(raw)["jobs"]], [DIGEST, ALERTS, EXTRA])
        for path, key in ((f"/api/replies?job={DIGEST}&q=bob&limit=5", "items"),
                          (f"/api/mentions?job={DIGEST}&hours=24", "items"),
                          (f"/api/activity?job={DIGEST}&limit=3", "items"), ("/api/reviews", "rows")):
            code, _, raw = self.req("GET", path)
            self.assertEqual(code, 200, path)
            self.assertIn(key, json.loads(raw))
        self.assertEqual(self.req("GET", "/api/replies?job=zzz000")[0], 400)
        self.assertEqual(self.req("GET", "/api/replies?limit=x")[0], 400)
        self.assertEqual(self.req("GET", "/nope")[0], 404)

    def test_host_guard(self):
        self.assertEqual(self.req("GET", "/api/status", Host="evil.example")[0], 403)
        self.assertEqual(self.req("GET", "/", Host=f"evil.example:{self.port}")[0], 403)
        self.assertEqual(self.req("GET", "/api/status", Host=f"localhost:{self.port}")[0], 200)
        self.assertEqual(self.post({"job": DIGEST, "action": "pause"}, Host="evil.example")[0], 403)
        self.assertEqual(self.calls(), [])

    def test_csrf_and_origin(self):
        body = {"job": DIGEST, "action": "pause"}
        self.assertEqual(self.req("POST", "/api/control", body)[0], 403)
        self.assertEqual(self.post(body, token="wrong")[0], 403)
        self.assertEqual(self.post(body, Origin="http://evil.example")[0], 403)
        self.assertEqual(self.post(body, Origin=f"http://127.0.0.1:{self.port + 1}")[0], 403)
        self.assertEqual(self.req("POST", "/api/live?hours=1")[0], 403)
        self.assertEqual(self.calls(), [])

    def test_control(self):
        self.assertEqual(self.post({"job": "zzz000", "action": "pause"})[0], 400)
        self.assertEqual(self.post({"job": DIGEST, "action": "explode"})[0], 400)
        self.assertEqual(self.post({"job": DIGEST, "action": "pause_until", "until": "x"})[0], 400)
        self.assertEqual(self.post([1])[0], 400)
        self.assertEqual(self.req("POST", "/api/control", None, X_CSRF_Token=self.srv.token)[0], 400)
        self.assertEqual(self.calls(), [])
        code, ctype, raw = self.post({"job": DIGEST, "action": "pause"},
                                     Origin=f"http://localhost:{self.port}")
        self.assertEqual((code, ctype), (200, "application/json"))
        r = json.loads(raw)
        self.assertEqual((r["ok"], r["status"]["id"]), (True, DIGEST))
        self.assertEqual(self.calls(), [["cron", "pause", DIGEST]])

    def test_job_override(self):
        self.start(["zzz000"])
        self.assertEqual([j["id"] for j in json.loads(self.req("GET", "/api/status")[2])["jobs"]],
                         ["zzz000"])
        self.assertEqual(self.post({"job": DIGEST, "action": "pause"})[0], 400)
        self.assertEqual(self.post({"job": "zzz000", "action": "pause"})[0], 200)


class ReadOnlyTest(Base):
    def test_databases_are_never_modified(self):
        dbs = [self.home / "state.db", self.home / "cron" / "executions.db"]
        before = [(digest(p), p.stat().st_mtime_ns) for p in dbs]
        listing = sorted(p.name for d in (self.home, self.home / "cron") for p in d.iterdir())
        dash.replies(DIGEST, q="bob")
        dash.mentions(DIGEST, hours=720)
        dash.activity(DIGEST)
        dash.status()
        dash.reviews()
        self.assertEqual([(digest(p), p.stat().st_mtime_ns) for p in dbs], before)
        self.assertEqual(sorted(p.name for d in (self.home, self.home / "cron") for p in d.iterdir()),
                         listing)  # no journal/wal files left behind
        with self.assertRaises(sqlite3.OperationalError):
            with dash.ro(dbs[0]) as c:
                c.execute("DELETE FROM sessions")

    def test_ro_retries_immutable_when_plain_open_fails(self):
        real, calls = sqlite3.connect, []

        def connect(target, **kw):
            calls.append(target)
            if len(calls) == 1:
                raise sqlite3.OperationalError("unable to open database file")
            return real(target, **kw)

        with mock.patch.object(dash.sqlite3, "connect", side_effect=connect):
            c = dash.ro(self.home / "cron" / "executions.db")
            try:
                self.assertGreater(c.execute("SELECT count(*) FROM sqlite_master").fetchone()[0], 0)
            finally:
                c.close()
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith("?mode=ro"))
        self.assertTrue(calls[1].endswith("?mode=ro&immutable=1"))


class CliTest(Base):
    def test_check(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(dash.main(["--check"]), 0)
        out = buf.getvalue()
        for want in (DIGEST, ALERTS, "jobs.json", "executions.db", "state.db"):
            self.assertIn(want, out)
        self.assertNotIn("zzz000", out)

    def test_refuses_non_loopback_host(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            dash.main(["--host", "0.0.0.0", "--check"])


if __name__ == "__main__":
    unittest.main()
