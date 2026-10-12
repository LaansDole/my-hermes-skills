#!/usr/bin/env python3
"""Tests for skills/slack/slack-mention-watch/scripts/watch_mentions.py (no network).

Run:  python3 -m unittest -v tests.test_watch_mentions
"""

import email.message
import importlib.util
import io
import json
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parent.parent / "skills/slack/slack-mention-watch/scripts/watch_mentions.py"
_spec = importlib.util.spec_from_file_location("watch_mentions_under_test", SCRIPT)
wm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(wm)

UID = "U0BJAUSC83Y"
BOT_UID = "U0HERMESBOT"


class FakeResp(io.BytesIO):
    def __init__(self, payload):
        super().__init__(json.dumps(payload).encode())
        self.headers = email.message.Message()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeSlack:
    """Routes requests by Slack method name; records every request."""

    def __init__(self, routes):
        # bot identity lookup (auth.test on SLACK_BOT_TOKEN) happens whenever there are matches
        self.routes, self.requests = {"auth.test": {"ok": True, "user_id": BOT_UID}, **routes}, []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        method = urllib.parse.urlparse(req.full_url).path.rsplit("/", 1)[1]
        r = self.routes[method]
        r = r(req) if callable(r) else r
        if isinstance(r, Exception):
            raise r
        return FakeResp(r)

    def methods(self):
        return [urllib.parse.urlparse(r.full_url).path.rsplit("/", 1)[1] for r in self.requests]


def search_payload(*matches):
    return {"ok": True, "messages": {"matches": list(matches)}}


def match(ts, user="U1ALICE", text=f"hey <@{UID}> look", **kw):
    m = {"ts": ts, "user": user, "username": "alice", "text": text,
         "channel": {"id": "C1", "name": "general"}, "permalink": f"https://x/p{ts}"}
    m.update(kw)
    return m


def http_429():
    hdrs = email.message.Message()
    hdrs["Retry-After"] = "1"
    return urllib.error.HTTPError("https://slack.com/api/x", 429, "Too Many", hdrs, None)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.state = d / "state.json"
        dotenv = d / ".env"
        dotenv.write_text(f"SLACK_ALLOWED_USERS={UID},U9OTHER\nSLACK_BOT_TOKEN=xoxb-bot\n")
        self.env = {"HERMES_DOTENV": str(dotenv), "SLACK_MENTION_STATE_FILE": str(self.state),
                    "SLACK_USER_READ_TOKEN": "xoxp-user"}
        patches = [mock.patch.dict(os.environ, self.env, clear=True),
                   mock.patch.object(wm.time, "sleep")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)
        # last_ts well in the past so test fixtures count as new
        self.write_state("1000.000000", [])

    def write_state(self, last_ts, seen):
        self.state.write_text(json.dumps({"last_ts": last_ts, "seen": seen}))

    def read_state(self):
        return json.loads(self.state.read_text())

    def run_main(self, fake, *argv):
        buf = io.StringIO()
        with mock.patch.object(wm, "urlopen", fake), redirect_stdout(buf):
            code = wm.main(list(argv))
        return code, buf.getvalue()


class ReadOnly(Base):
    def test_write_methods_rejected_before_any_request(self):
        fake = FakeSlack({})
        with mock.patch.object(wm, "urlopen", fake):
            for method in ("chat.postMessage", "reactions.add", "conversations.join",
                           "conversations.mark", "chat.delete"):
                with self.assertRaises(ValueError):
                    wm.api(method, "xoxp-user", channel="C1")
        self.assertEqual(fake.requests, [])

    def test_only_get_without_body(self):
        fake = FakeSlack({"search.messages": search_payload(match("2000.000100")),
                          "users.info": {"ok": True, "user": {"name": "tony"}}})
        self.run_main(fake)
        fake2 = FakeSlack({"auth.test": {"ok": True, "user": "tony"},
                           "search.messages": search_payload()})
        self.run_main(fake2, "--check")
        for req in fake.requests + fake2.requests:
            self.assertEqual(req.get_method(), "GET")
            self.assertIsNone(req.data)
            self.assertIn(urllib.parse.urlparse(req.full_url).path.rsplit("/", 1)[1], wm.READ_METHODS)


class Modes(Base):
    def test_user_token_uses_search(self):
        fake = FakeSlack({"search.messages": search_payload()})
        self.run_main(fake)
        self.assertEqual(fake.methods(), ["search.messages"])
        q = urllib.parse.parse_qs(urllib.parse.urlparse(fake.requests[0].full_url).query)
        self.assertEqual(q["query"], [f"<@{UID}>"])
        self.assertEqual(fake.requests[0].headers["Authorization"], "Bearer xoxp-user")

    def test_no_user_token_uses_history_with_bot_token(self):
        del os.environ["SLACK_USER_READ_TOKEN"]
        fake = FakeSlack({
            "conversations.list": {"ok": True, "channels": [
                {"id": "C1", "name": "general", "is_member": True},
                {"id": "C2", "name": "random", "is_member": False}]},
            "conversations.history": {"ok": True, "messages": [
                {"ts": "2000.1", "user": "U1ALICE", "text": f"<@{UID}> ping"},
                {"ts": "2000.2", "user": "U1ALICE", "text": "unrelated"}]},
            "users.info": {"ok": True, "user": {"profile": {"display_name": "alice"}}},
            "chat.getPermalink": {"ok": True, "permalink": "https://x/perm"},
        })
        code, out = self.run_main(fake)
        self.assertEqual(code, 0)
        self.assertNotIn("search.messages", fake.methods())
        hist = [r for r in fake.requests if "conversations.history" in r.full_url]
        self.assertEqual(len(hist), 1)  # non-member channel skipped
        self.assertIn("channel=C1", hist[0].full_url)
        self.assertEqual(hist[0].headers["Authorization"], "Bearer xoxb-bot")
        self.assertEqual(out.count("Slack mention"), 1)
        self.assertIn("https://x/perm", out)


class Filtering(Base):
    def test_self_and_bot_messages_dropped(self):
        fake = FakeSlack({"search.messages": search_payload(
            match("2000.1", user=UID),
            match("2000.2", subtype="bot_message"),
            match("2000.3", bot_id="B1"),
            match("2000.4", text=f"real <@{UID}>"),
        ), "users.info": {"ok": True, "user": {"name": "tony"}}})
        _, out = self.run_main(fake)
        self.assertEqual(out.count("Slack mention"), 1)
        self.assertIn("real @tony", out)

    def test_dedupe_across_runs(self):
        routes = {"search.messages": search_payload(match("2000.1")),
                  "users.info": {"ok": True, "user": {"name": "tony"}}}
        _, first = self.run_main(FakeSlack(routes))
        self.assertIn("Slack mention", first)
        # second run: same message still in search results (overlap window)
        self.write_state("2000.1", self.read_state()["seen"])
        _, second = self.run_main(FakeSlack(routes))
        self.assertEqual(second, "")

    def test_nothing_new_prints_nothing(self):
        code, out = self.run_main(FakeSlack({"search.messages": search_payload()}))
        self.assertEqual((code, out), (0, ""))

    def test_older_than_window_ignored(self):
        self.write_state("5000.0", [])
        _, out = self.run_main(FakeSlack({"search.messages": search_payload(match("100.0"))}))
        self.assertEqual(out, "")


class State(Base):
    def test_dry_run_does_not_touch_state(self):
        before = self.state.read_text()
        fake = FakeSlack({"search.messages": search_payload(match("2000.1")),
                          "users.info": {"ok": True, "user": {"name": "tony"}}})
        _, out = self.run_main(fake, "--dry-run")
        self.assertIn("Slack mention", out)
        self.assertEqual(self.state.read_text(), before)

    def test_429_skips_tick_without_advancing(self):
        before = self.state.read_text()
        fake = FakeSlack({"search.messages": lambda req: http_429()})
        code, out = self.run_main(fake)
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(fake.methods(), ["search.messages", "search.messages"])  # one retry
        wm.time.sleep.assert_called_once_with(1)
        self.assertEqual(self.state.read_text(), before)

    def test_successful_run_advances_and_is_private(self):
        self.run_main(FakeSlack({"search.messages": search_payload()}))
        self.assertGreater(float(self.read_state()["last_ts"]), 1000.0)
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)

    def test_auth_error_prints_one_line_and_exits_1(self):
        before = self.state.read_text()
        code, out = self.run_main(FakeSlack({"search.messages": {"ok": False, "error": "invalid_auth"}}))
        self.assertEqual(code, 1)
        self.assertEqual(out, "[slack-mention-watch] ERROR: search.messages: invalid_auth\n")
        self.assertEqual(self.state.read_text(), before)


class Formatting(Base):
    def test_mentions_resolved_and_truncated(self):
        names = {"U0BJAUSC83Y": "tony", "U2BOB": "bob"}
        name = lambda uid: names[uid]
        self.assertEqual(wm.render_text(f"hi <@{UID}> and <@U2BOB|bobby> in <#C1|general> <!here>", name),
                         "hi @tony and @bobby in #general @here")
        self.assertEqual(wm.render_text(f"<@U2BOB> " + "x" * 1000, name)[:5], "@bob ")
        self.assertEqual(len(wm.render_text("x" * 1000, name)), wm.TEXT_MAX)

    def test_users_info_resolves_display_name(self):
        fake = FakeSlack({"search.messages": search_payload(match("2000.1", text=f"<@{UID}> yo")),
                          "users.info": {"ok": True, "user": {"name": "t", "profile": {"display_name": "tony"}}}})
        _, out = self.run_main(fake)
        self.assertIn("> @tony yo", out)
        self.assertIn("#general from alice", out)
        self.assertIn("https://x/p2000.1", out)


class SelfAlertLoop(Base):
    NAMES = {"ok": True, "user": {"profile": {"display_name": "tony"}}}

    def test_home_channel_matches_dropped(self):
        os.environ["SLACK_HOME_CHANNEL"] = "D0HOME"
        fake = FakeSlack({"search.messages": search_payload(
            match("2000.1", user="U1ALICE", channel={"id": "D0HOME", "is_im": True}),
            match("2000.2")), "users.info": self.NAMES})
        _, out = self.run_main(fake)
        self.assertEqual(out.count("Slack mention"), 1)
        self.assertIn("p2000.2", out)
        self.assertNotIn("D0HOME", self.read_state()["seen"][0])

    def test_home_channel_read_from_dotenv(self):
        dotenv = Path(os.environ["HERMES_DOTENV"])
        dotenv.write_text(dotenv.read_text() + "SLACK_HOME_CHANNEL=C1\n")
        _, out = self.run_main(FakeSlack({"search.messages": search_payload(match("2000.1"))}))
        self.assertEqual(out, "")

    def test_bot_and_ignored_authors_dropped(self):
        os.environ["SLACK_MENTION_IGNORE_USERS"] = "U7HOOK, U8OTHER"
        fake = FakeSlack({"search.messages": search_payload(
            match("2000.1", user=BOT_UID, username="hermes"),  # no bot_id in search matches
            match("2000.2", user="U7HOOK"),
            match("2000.3", user="U8OTHER"),
            match("2000.4")), "users.info": self.NAMES})
        _, out = self.run_main(fake)
        self.assertEqual(out.count("Slack mention"), 1)
        self.assertIn("p2000.4", out)
        auth = [r for r in fake.requests if "auth.test" in r.full_url]
        self.assertEqual(len(auth), 1)
        self.assertEqual(auth[0].headers["Authorization"], "Bearer xoxb-bot")

    def test_no_bot_token_skips_bot_check(self):
        Path(os.environ["HERMES_DOTENV"]).write_text(f"SLACK_ALLOWED_USERS={UID}\n")
        fake = FakeSlack({"search.messages": search_payload(match("2000.1")),
                          "users.info": self.NAMES})
        _, out = self.run_main(fake)
        self.assertNotIn("auth.test", fake.methods())
        self.assertIn("Slack mention", out)

    def test_rendered_alert_has_no_mention_markup(self):
        for users_info in (self.NAMES, {"ok": False, "error": "missing_scope"}):
            self.write_state("1000.000000", [])
            fake = FakeSlack({"search.messages": search_payload(
                match("2000.1", text=f"<@{UID}> and <@U2BOB> see <@{UID}|tony>")),
                "users.info": users_info})
            _, out = self.run_main(fake)
            self.assertIn("Slack mention", out)
            self.assertNotIn("<@", out)
            self.assertNotIn(UID, out)

    def test_users_info_uses_bot_token(self):
        fake = FakeSlack({"search.messages": search_payload(match("2000.1", text=f"<@{UID}> yo")),
                          "users.info": self.NAMES})
        self.run_main(fake)
        infos = [r for r in fake.requests if "users.info" in r.full_url]
        self.assertTrue(infos)
        self.assertTrue(all(r.headers["Authorization"] == "Bearer xoxb-bot" for r in infos))
        search = [r for r in fake.requests if "search.messages" in r.full_url]
        self.assertEqual(search[0].headers["Authorization"], "Bearer xoxp-user")


if __name__ == "__main__":
    unittest.main()
