#!/usr/bin/env python3
"""Read-only Slack poller: print NEW messages that @-mention one user.

Built for a Hermes cron job with --no-agent: empty stdout = nothing delivered.

Modes (auto-selected):
  search  -- SLACK_USER_READ_TOKEN (xoxp, scope search:read) -> search.messages.
             Covers every channel/DM the user can see. One call per tick.
  history -- fallback, SLACK_BOT_TOKEN -> conversations.history over channels
             the bot is a member of. Top-level messages only (no thread replies).

Read-only guarantee: every request goes through api(), which only issues HTTP
GET to methods in READ_METHODS and raises on anything else.

Env (process env first, then the dotenv file -- Hermes strips SLACK_* from
subprocess env, so the file is the real source):
  SLACK_USER_READ_TOKEN, SLACK_BOT_TOKEN
  SLACK_MENTION_USER_ID      default: first id of SLACK_ALLOWED_USERS
  SLACK_MENTION_IGNORE_USERS extra author ids to drop (comma list); the bot's own
                             user id (auth.test on SLACK_BOT_TOKEN) is always dropped
  SLACK_HOME_CHANNEL         alert delivery channel; matches in it are dropped
  SLACK_MENTION_LOOKBACK_MINS first-run lookback, default 60
  SLACK_MENTION_STATE_FILE   default ~/.hermes/scripts/.slack-mention-watch.json
  HERMES_DOTENV              default ~/.hermes/.env

Flags: --dry-run (don't save state), --check (diagnostics, no state).
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from urllib.request import urlopen

API = "https://slack.com/api"
TAG = "[slack-mention-watch]"
READ_METHODS = frozenset({
    "auth.test", "search.messages", "conversations.list", "conversations.history",
    "conversations.info", "users.info", "chat.getPermalink",
})
# ponytail: re-scan this far behind last_ts each tick so late-indexed search
# results aren't lost; `seen` dedupes the overlap.
OVERLAP_SECS = 600
SEEN_MAX = 500
TEXT_MAX = 400
CHANNEL_SLEEP = 1.2


class SlackError(Exception):
    pass


class RateLimited(Exception):
    pass


def _path(env_name, default):
    return os.path.expanduser(os.environ.get(env_name) or default)


def dotenv(name):
    try:
        with open(_path("HERMES_DOTENV", "~/.hermes/.env")) as f:
            for line in f:
                line = line.strip()
                if line.startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip("'\"") or None
    except OSError:
        pass
    return None


def env(name):
    return os.environ.get(name) or dotenv(name)


def api(method, token, _headers=None, **params):
    """GET a read-only Slack method. Retries once after a 429, then RateLimited."""
    if method not in READ_METHODS:
        raise ValueError(f"refusing non-read Slack method: {method}")
    url = f"{API}/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": f"Bearer {token}"})
    for attempt in (1, 2):
        try:
            with urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if _headers is not None:
                    _headers.update(resp.headers.items())
            break
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise SlackError(f"{method}: HTTP {e.code}")
            if attempt == 2:
                raise RateLimited(method)
            time.sleep(min(int(e.headers.get("Retry-After") or 30), 60))
    if not data.get("ok"):
        if data.get("error") == "ratelimited":
            raise RateLimited(method)
        raise SlackError(f"{method}: {data.get('error')}")
    return data


def load_state(path, lookback_mins):
    try:
        with open(path) as f:
            s = json.load(f)
        return {"last_ts": str(s["last_ts"]), "seen": list(s.get("seen", []))}
    except (OSError, ValueError, KeyError):
        return {"last_ts": f"{time.time() - lookback_mins * 60:.6f}", "seen": []}


def save_state(path, state):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as f:
        json.dump(state, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def is_noise(m, uid):
    return (m.get("user") == uid or m.get("subtype") == "bot_message"
            or bool(m.get("bot_id")))


def search_mentions(token, uid, floor):
    d = api("search.messages", token, query=f"<@{uid}>", sort="timestamp",
            sort_dir="desc", count=50)
    out = []
    for m in d.get("messages", {}).get("matches", []):
        if float(m["ts"]) <= floor or is_noise(m, uid):
            continue
        ch = m.get("channel") or {}
        out.append({
            "channel_id": ch.get("id", ""),
            "channel": "DM" if ch.get("is_im") else f"#{ch.get('name', '?')}",
            "user": m.get("user"), "username": m.get("username"),
            "ts": m["ts"], "text": m.get("text", ""),
            "permalink": m.get("permalink", ""),
        })
    return out


def member_channels(token):
    chans, cursor = [], ""
    while True:
        # ponytail: bot<->user IMs (no is_member flag) skipped; @tony in a DM to the bot is noise.
        d = api("conversations.list", token, types="public_channel,private_channel,mpim",
                exclude_archived="true", limit=200, cursor=cursor)
        chans += [c for c in d.get("channels", []) if c.get("is_member")]
        cursor = (d.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            return chans


def history_mentions(token, uid, floor):
    # ponytail: top-level messages only; thread replies would need
    # conversations.replies per thread (N extra Tier-3 calls). Add if missed.
    needle, out = f"<@{uid}>", []
    for i, c in enumerate(member_channels(token)):
        if i:
            time.sleep(CHANNEL_SLEEP)
        cursor = ""
        while True:
            d = api("conversations.history", token, channel=c["id"],
                    oldest=f"{floor:.6f}", limit=200, cursor=cursor)
            for m in d.get("messages", []):
                if needle in m.get("text", "") and not is_noise(m, uid):
                    out.append({
                        "channel_id": c["id"],
                        "channel": f"#{c.get('name', '?')}",
                        "user": m.get("user"), "username": None,
                        "ts": m["ts"], "text": m["text"], "permalink": "",
                    })
            cursor = (d.get("response_metadata") or {}).get("next_cursor")
            if not cursor:
                break
    return out


class Names:
    """users.info lookups. `me` (the watched user) never falls back to a raw id,
    so a rendered alert can't be re-indexed as a fresh mention."""

    def __init__(self, token, me):
        self.token, self.me, self.cache = token, me, {}

    def __call__(self, uid):
        if uid not in self.cache:
            fallback = "me" if uid == self.me else uid
            try:
                u = api("users.info", self.token, user=uid)["user"]
                p = u.get("profile") or {}
                self.cache[uid] = (p.get("display_name") or u.get("real_name")
                                   or u.get("name") or fallback)
            except SlackError:
                self.cache[uid] = fallback
        return self.cache[uid]


def render_text(text, name):
    text = re.sub(r"<@([UW][A-Z0-9]+)(?:\|([^>]*))?>",
                  lambda mm: "@" + (mm.group(2) or name(mm.group(1))), text)
    text = re.sub(r"<#C[A-Z0-9]+\|([^>]*)>", r"#\1", text)
    text = re.sub(r"<!(here|channel|everyone)[^>]*>", r"@\1", text)
    return text if len(text) <= TEXT_MAX else text[:TEXT_MAX - 1] + "…"


def fmt(m, name, token):
    sender = m["username"] or (name(m["user"]) if m["user"] else "unknown")
    when = datetime.fromtimestamp(float(m["ts"])).strftime("%Y-%m-%d %H:%M")
    link = m["permalink"]
    if not link and m["channel_id"]:
        try:
            link = api("chat.getPermalink", token, channel=m["channel_id"],
                       message_ts=m["ts"]).get("permalink", "")
        except SlackError:
            link = ""
    lines = [f"Slack mention in {m['channel']} from {sender} at {when}",
             "> " + render_text(m["text"], name).replace("\n", "\n> ")]
    if link:
        lines.append(link)
    return "\n".join(lines)


def ignored_users(bot_tok):
    ids = {u.strip() for u in (env("SLACK_MENTION_IGNORE_USERS") or "").split(",") if u.strip()}
    if bot_tok:
        try:
            ids.add(api("auth.test", bot_tok)["user_id"])
        except SlackError:
            pass
    return ids


def config():
    uid = env("SLACK_MENTION_USER_ID") or (env("SLACK_ALLOWED_USERS") or "").split(",")[0].strip()
    user_tok = env("SLACK_USER_READ_TOKEN")
    if user_tok:
        return uid, "search", user_tok
    return uid, "history", env("SLACK_BOT_TOKEN")


def run(dry_run=False):
    uid, mode, token = config()
    if not uid or not token:
        raise SlackError("missing SLACK_MENTION_USER_ID/SLACK_ALLOWED_USERS or token")
    bot_tok = env("SLACK_BOT_TOKEN")
    state_path = _path("SLACK_MENTION_STATE_FILE", "~/.hermes/scripts/.slack-mention-watch.json")
    state = load_state(state_path, float(env("SLACK_MENTION_LOOKBACK_MINS") or 60))
    started = time.time()
    floor = float(state["last_ts"]) - OVERLAP_SECS
    found = (search_mentions if mode == "search" else history_mentions)(token, uid, floor)
    if found:
        # Alerts are posted into SLACK_HOME_CHANNEL by the bot and quote the mention,
        # so search would return them as new mentions forever. Drop both ways.
        home, bots = env("SLACK_HOME_CHANNEL"), ignored_users(bot_tok)
        found = [m for m in found if m["channel_id"] != home and m["user"] not in bots]
    seen = set(state["seen"])
    new = []
    for m in sorted(found, key=lambda m: float(m["ts"])):
        key = f"{m['channel_id']}:{m['ts']}"
        if key not in seen:
            seen.add(key)
            state["seen"].append(key)
            new.append(m)
    name = Names(bot_tok or token, uid)  # bot token has users:read; user token usually not
    out = "\n\n".join(fmt(m, name, token) for m in new)
    if not dry_run:
        state["last_ts"] = f"{max(started, float(state['last_ts'])):.6f}"
        state["seen"] = state["seen"][-SEEN_MAX:]
        save_state(state_path, state)
    return out


def check():
    uid, mode, token = config()
    if not token:
        raise SlackError("no SLACK_USER_READ_TOKEN or SLACK_BOT_TOKEN found")
    hdrs = {}
    who = api("auth.test", token, _headers=hdrs)
    scopes = {k.lower(): v for k, v in hdrs.items()}.get("x-oauth-scopes", "?")
    lines = [f"mode: {mode}", f"token type: {token.split('-')[0]}",
             f"auth: {who.get('user')} ({who.get('user_id')}) team {who.get('team')}",
             f"scopes: {scopes}", f"watching: <@{uid}>"]
    if mode == "search":
        d = api("search.messages", token, query=f"<@{uid}>", count=1)
        lines.append(f"search ok: {d.get('messages', {}).get('total', 0)} total mentions indexed")
    else:
        lines.append(f"member channels: {len(member_channels(token))}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="don't save state")
    ap.add_argument("--check", action="store_true", help="print diagnostics, no state")
    a = ap.parse_args(argv)
    try:
        out = check() if a.check else run(a.dry_run)
    except RateLimited as e:
        print(f"{TAG} rate limited on {e}; skipping tick", file=sys.stderr)
        return 0
    except urllib.error.URLError as e:
        # ponytail: network blips (laptop asleep, wifi) stay off stdout so cron doesn't spam.
        print(f"{TAG} network error: {e.reason}; skipping tick", file=sys.stderr)
        return 0
    except SlackError as e:
        print(f"{TAG} ERROR: {e}")
        return 1
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
