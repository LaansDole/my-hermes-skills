#!/usr/bin/env python3
"""Slack mention poller: print NEW messages that @-mention one user.

Built for a Hermes cron job with --no-agent: empty stdout = nothing delivered.

Modes (auto-selected):
  search  -- SLACK_USER_READ_TOKEN (xoxp, scope search:read) -> search.messages.
             Covers every channel/DM the user can see. One call per tick.
  history -- fallback, SLACK_BOT_TOKEN -> conversations.history over channels
             the bot is a member of. Top-level messages only (no thread replies).

Write guarantee: reads go through api() -- HTTP GET to READ_METHODS only, raising
on anything else. The one write is opt-in (--react / SLACK_MENTION_REACT) and goes
through api_write(), which POSTs only WRITE_METHODS ({"reactions.add"}).
Jev shadow mode (SLACK_MENTION_JEV_SHADOW) sends each new mention's text and thread to
api.typesafe.ai, a third party, so it is opt-in. It only logs Jev's probabilities beside
the regex result; nothing acts on them and stdout is unchanged.

Env (process env first, then the dotenv file -- Hermes strips SLACK_* from
subprocess env, so the file is the real source):
  SLACK_USER_READ_TOKEN, SLACK_BOT_TOKEN
  SLACK_USER_REACT_TOKEN     token for reactions.add, default SLACK_USER_READ_TOKEN
  SLACK_MENTION_REACT        1/true/yes = auto-react, same as --react
  SLACK_MENTION_REACT_DELAY_SECS  a reaction is never sent sooner than this many
                             seconds after the mention, default 60; 0 = no wait
  SLACK_MENTION_USER_ID      default: owner of SLACK_USER_READ_TOKEN (auth.test),
                             else first id of SLACK_ALLOWED_USERS
  SLACK_MENTION_IGNORE_USERS extra author ids to drop (comma list); the bot's own
                             user id (auth.test on SLACK_BOT_TOKEN) is always dropped
  SLACK_HOME_CHANNEL         alert delivery channel; matches in it are dropped
  SLACK_MENTION_LOOKBACK_MINS first-run lookback, default 60
  SLACK_MENTION_STATE_FILE   default ~/.hermes/scripts/.slack-mention-watch.json
  HERMES_DOTENV              default ~/.hermes/.env
  SLACK_MENTION_JEV_SHADOW   1/true/yes = log Jev scores per new mention (needs TYPESAFE_API_KEY)
  SLACK_MENTION_JEV_LOG      default ~/.hermes/scripts/.slack-mention-jev.jsonl
  TYPESAFE_API_KEY           Jev API key, shadow mode only

Flags: --dry-run (don't save state), --check (diagnostics, no state),
       --recent [HOURS] (list all mentions in the last HOURS, default 24; ignores
       and never writes state),
       --digest (same tick/state as default, but print a context block with each
       mention's thread for an LLM cron agent; nothing new -> {"wakeAgent": false}),
       --react (react to each new mention: :eyes: to questions/requests,
       :raised_hands: to thanks, :memo: to FYI; default and --digest ticks only,
       needs the user scope reactions:write).
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
    "conversations.info", "conversations.replies", "users.info", "chat.getPermalink",
})
WRITE_METHODS = frozenset({"reactions.add"})  # the only write, opt-in via --react
# ponytail: re-scan this far behind last_ts each tick so late-indexed search
# results aren't lost; `seen` dedupes the overlap.
OVERLAP_SECS = 600
SEEN_MAX = 500
TEXT_MAX = 400
CHANNEL_SLEEP = 1.2
RECENT_MAX = 50
REACT_DELAY_SECS = 60.0  # an instant reaction looks like a bot; wait this long after the mention
THREAD_MAX = 20     # messages of thread context per mention
THREAD_TEXT_MAX = 600
DIGEST_MAX = 12000  # chars; oldest thread lines dropped first, mentions always kept
WAKE_FALSE = '{"wakeAgent": false}'
JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_HI = 0.9  # ponytail: placeholder band until the shadow log says where to cut
JEV_Q = {k: {"type": "noul", "instructions": q} for k, q in {
    "request": "Does the mention ask the watched user to do something, answer a question, or take an action (including implicitly, e.g. someone is blocked on them)?",
    "thanks": "Is the mention mainly thanking or appreciating the watched user?",
    "fyi": "Is the mention only informing the watched user (status, FYI, done, merged, approved) with nothing for them to do?",
    "handled": "Based on the thread, has the watched user already committed to or handled this, or is it already resolved, so no further action is needed from them?",
    # same text as review_spawn.py's review gate, so the shadow log calibrates its threshold
    "review": "Is the watched user being asked to review, check, test, verify or approve a specific pull request, ticket, fix or deployment (not edit their own message, update a list, answer a question, or do other work)?",
}.items()}


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


def _send(req, method, _headers=None, ok_errors=()):
    """One Slack call: retry once after a 429, then RateLimited; raise on `ok: false`."""
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
    if not data.get("ok") and data.get("error") not in ok_errors:
        if data.get("error") == "ratelimited":
            raise RateLimited(method)
        raise SlackError(f"{method}: {data.get('error')}")
    return data


def api(method, token, _headers=None, **params):
    """GET a read-only Slack method."""
    if method not in READ_METHODS:
        raise ValueError(f"refusing non-read Slack method: {method}")
    url = f"{API}/{method}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": f"Bearer {token}"})
    return _send(req, method, _headers)


def api_write(method, token, **params):
    """POST the one allowlisted write. `already_reacted` is success, not an error."""
    if method not in WRITE_METHODS:
        raise ValueError(f"refusing non-allowlisted Slack write: {method}")
    req = urllib.request.Request(
        f"{API}/{method}", data=urllib.parse.urlencode(params).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/x-www-form-urlencoded"})
    return _send(req, method, ok_errors=("already_reacted",))


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


def search_mentions(token, uid, floor, count=50, pages=1):
    out = []
    for page in range(1, pages + 1):
        d = api("search.messages", token, query=f"<@{uid}>", sort="timestamp",
                sort_dir="desc", count=count, page=page)
        msgs = d.get("messages", {})
        matches = msgs.get("matches", [])
        for m in matches:
            if float(m["ts"]) <= floor or is_noise(m, uid):
                continue
            ch = m.get("channel") or {}
            out.append({
                "channel_id": ch.get("id", ""),
                "channel": "DM" if ch.get("is_im") else f"#{ch.get('name', '?')}",
                "user": m.get("user"), "username": m.get("username"),
                "ts": m["ts"], "text": m.get("text", ""), "thread_ts": m.get("thread_ts"),
                "permalink": m.get("permalink", ""),
            })
        # newest first: once a page reaches the floor, older pages can't matter
        if (not matches or float(matches[-1]["ts"]) <= floor
                or page >= (msgs.get("paging") or {}).get("pages", 1)):
            break
    return out


def member_channels(token):
    chans, cursor = [], ""
    while True:
        # ponytail: bot<->user IMs (no is_member flag) skipped; @you in a DM to the bot is noise.
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
                        "ts": m["ts"], "text": m["text"], "thread_ts": m.get("thread_ts"),
                        "permalink": "",
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


def render_text(text, name, limit=TEXT_MAX, unescape=False):
    text = re.sub(r"<@([UW][A-Z0-9]+)(?:\|([^>]*))?>",
                  lambda mm: "@" + (mm.group(2) or name(mm.group(1))), text)
    text = re.sub(r"<#C[A-Z0-9]+\|([^>]*)>", r"#\1", text)
    text = re.sub(r"<!(here|channel|everyone)[^>]*>", r"@\1", text)
    if unescape:  # Slack escapes only these three
        text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def sender_of(m, name):
    return m.get("username") or (name(m["user"]) if m.get("user") else "unknown")


def permalink(m, token):
    if m["permalink"] or not m["channel_id"]:
        return m["permalink"]
    try:
        return api("chat.getPermalink", token, channel=m["channel_id"],
                   message_ts=m["ts"]).get("permalink", "")
    except SlackError:
        return ""


def when(ts, f="%a %Y-%m-%d %H:%M"):
    """Local time with weekday, so readers (and the digest LLM) never guess the day."""
    return datetime.fromtimestamp(float(ts)).strftime(f)


def fmt(m, name, token, status=None):
    link = permalink(m, token)
    lines = [f"Slack mention in {m['channel']} from {sender_of(m, name)} at {when(m['ts'])}",
             "> " + render_text(m["text"], name).replace("\n", "\n> ")]
    if link:
        lines.append(link)
    if status:
        lines.append(f"Reacted: {status}")
    return "\n".join(lines)


def thread_root(m):
    """ts of the mention's thread root. search.messages matches never carry thread_ts;
    for a thread reply it is only in the permalink's query string."""
    query = urllib.parse.urlparse(m["permalink"]).query
    return (m.get("thread_ts") or urllib.parse.parse_qs(query).get("thread_ts", [None])[0]
            or m["ts"])


def thread(m, token, name):
    """[(ts, line)] oldest first: the thread root plus its latest replies, or an error string."""
    root = thread_root(m)
    try:
        msgs = api("conversations.replies", token, channel=m["channel_id"], ts=root,
                   limit=200).get("messages", [])
    except (SlackError, RateLimited, urllib.error.URLError) as e:
        return f"(thread context unavailable: {getattr(e, 'reason', None) or e})"
    msgs = sorted(msgs, key=lambda r: float(r["ts"]))
    if len(msgs) > THREAD_MAX:  # ponytail: one page; root + newest replies is enough context
        msgs = msgs[:1] + msgs[-(THREAD_MAX - 1):]
    out = []
    for r in msgs:
        who = (r.get("user") and name(r["user"])) or r.get("username") \
            or (r.get("bot_profile") or {}).get("name") or "bot"
        out.append((float(r["ts"]),
                    f"[{when(r['ts'], '%a %m-%d %H:%M')}] {who}: {digest_text(r.get('text', ''), name)}"))
    return out


def digest_text(text, name):
    return render_text(text, name, THREAD_TEXT_MAX, unescape=True).replace("\n", "\n    ")


def digest(new, name, token, uid, reacted=None, threads=None):
    """Plain-text context block for the cron agent, oldest mention first."""
    items, threads = [], threads or {}
    for m in new:
        head = [f"### Mention {len(items) + 1} -- {m['channel']} -- from {sender_of(m, name)}"
                f" at {when(m['ts'])}"]
        link = permalink(m, token)
        if link:
            head.append(f"Permalink: {link}")
        head.append("Mention: " + digest_text(m["text"], name))
        key = f"{m['channel_id']}:{m['ts']}"
        status = (reacted or {}).get(key)
        if status:
            head.append(f"Reacted: {status}")
        items.append((head, threads[key] if key in threads else thread(m, token, name)))

    now = datetime.now().astimezone()
    z = now.strftime("%z")
    z = z[:-2] if z.endswith("00") else z  # +0700 -> +07, keep +0530
    top = (f"NEW MENTIONS: {len(new)}   (watched user: @{name(uid)})"
           f"   now: {now.strftime('%a %Y-%m-%d %H:%M')} {z}")

    def render():
        blocks = [top]
        for head, t in items:
            tail = [t] if isinstance(t, str) else \
                [f"Thread ({len(t)} messages):"] + [line for _, line in t]
            blocks.append("\n".join(head + tail))
        return "\n\n".join(blocks)

    out = render()
    while len(out) > DIGEST_MAX:
        threads = [t for _, t in items if not isinstance(t, str) and t]
        if not threads:
            break
        oldest = min(threads, key=lambda t: t[0][0])
        del oldest[0]
        out = render()
    return out


# ponytail: deterministic rules, no LLM -- the digest cron agent is toolless on purpose.
MARKUP_RE = re.compile(r"<(?:https?:|mailto:)[^>]*>|<[@#!][^>]*>")
# Entries are regex fragments; ['\u2019] covers straight and curly apostrophes.
ASK = ("can you", "could you", "would you", "will you", "please", "pls", "plz", "review",
       "check", "take a look", "have a look", "help", "need you", "ptal", "any update",
       "any updates", "lmk", "let me know", "question\\w*", "let['\u2019]?s", "can we",
       "could we", "should we", "can i", "could i", "is it ok", "is it okay", "are you able",
       "wdyt", "thoughts")
THANKS = ("thanks", "thank you", "thank u", "thx", "ty", "tks",
          "c\u1ea3m \u01a1n", "c\u00e1m \u01a1n", "cam on")
FYI = ("fyi", "i['\u2019]ve commented", "i have commented", "i commented", "commented on",
       "commented in", "done", "merged", "deployed", "released", "approved", "lgtm",
       "resolved", "nvm")
ASK_RE = re.compile(r"\b(?:%s)\b" % "|".join(ASK), re.I)
THANKS_RE = re.compile(r"\b(?:%s)\b" % "|".join(THANKS), re.I)
FYI_RE = re.compile(r"\b(?:%s)\b" % "|".join(FYI), re.I)


def classify(text):
    """Emoji for a mention. Link/user markup is stripped first so a URL's "?" doesn't
    read as a question. Ask -> eyes beats thanks -> raised_hands beats FYI -> memo;
    anything else is a direct ping, which is a request by default (eyes)."""
    plain = MARKUP_RE.sub(" ", text or "")
    if "?" in plain or ASK_RE.search(plain):
        return "eyes"
    if THANKS_RE.search(plain):
        return "raised_hands"
    if FYI_RE.search(plain):
        return "memo"
    return "eyes"


def handled(m, token, uid):
    """Why this mention needs no reaction ("already reacted"/"already replied"), or None.
    One conversations.replies call from the thread root, starting at the mention (Slack
    returns only the message itself for a non-root ts): the watched user's own emoji on
    the mention counts, as does any answer of theirs after it."""
    try:
        msgs = api("conversations.replies", token, channel=m["channel_id"], ts=thread_root(m),
                   oldest=m["ts"], inclusive="true", limit=200).get("messages", [])
    except (SlackError, RateLimited, urllib.error.URLError):
        return None  # unknown -> react; a duplicate-looking emoji beats a missed one
    mine = [r for r in msgs if r["ts"] == m["ts"]]
    if any(uid in (rx.get("users") or []) for r in mine for rx in r.get("reactions") or []):
        return "already reacted"
    if any(r.get("user") == uid and float(r["ts"]) > float(m["ts"]) for r in msgs):
        return "already replied"
    return None


def react_enabled(flag):
    return bool(flag) or (env("SLACK_MENTION_REACT") or "").lower() in ("1", "true", "yes")


def react_delay():
    """Seconds a reaction must be no sooner than; 0 disables, bad values fall back."""
    try:
        d = float(env("SLACK_MENTION_REACT_DELAY_SECS") or REACT_DELAY_SECS)
    except ValueError:
        return REACT_DELAY_SECS
    return REACT_DELAY_SECS if d < 0 else d


def react(new, token, uid, dry_run=False):
    """Add one emoji per new mention. Returns {channel:ts -> status}; never raises."""
    delay, out = react_delay(), {}
    for m in new:
        key = f"{m['channel_id']}:{m['ts']}"
        emoji = classify(m["text"])
        if not emoji:
            out[key] = "none"
            continue
        if not dry_run:
            # Mentions come oldest first, so at most one real wait per tick: by the time
            # this one is sent the later ones are usually already due. The wait runs before
            # handled() so an emoji the user adds meanwhile still cancels ours.
            wait = float(m["ts"]) + delay - time.time()
            if wait > 0:
                time.sleep(min(wait, delay))
        skip = handled(m, token, uid)
        if skip:
            out[key] = f"none ({skip})"
        elif dry_run:
            out[key] = f":{emoji}: (dry run, not sent)"
        else:
            try:
                api_write("reactions.add", token, channel=m["channel_id"],
                          timestamp=m["ts"], name=emoji)
                out[key] = f":{emoji}:"
            except (SlackError, RateLimited, urllib.error.URLError) as e:
                err = getattr(e, "reason", None) or e
                print(f"{TAG} react failed on {key}: {err}", file=sys.stderr)
                out[key] = f"failed ({err})"
    return out


def jev(state, key):
    """One Jev call. Not api()/_send: those are Slack-only allowlists."""
    body = json.dumps({"state": state, "model": "jev-latest", "questions": JEV_Q}).encode()
    req = urllib.request.Request(JEV_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def jev_emoji(p):
    """Shadow policy, same order as classify(); None = Jev unsure, regex decides."""
    for q, emoji in (("request", "eyes"), ("thanks", "raised_hands"), ("fyi", "memo")):
        if p[q] >= JEV_HI:
            return emoji
    return None


def jev_shadow(new, token, uid, name, reacted, dry_run=False):
    """Log Jev's scores beside the regex result for each new mention; no stdout.
    Returns {channel:ts -> thread()} so digest() can reuse them instead of refetching."""
    threads = {}
    key = env("TYPESAFE_API_KEY")
    if not key or (env("SLACK_MENTION_JEV_SHADOW") or "").lower() not in ("1", "true", "yes"):
        return threads
    log = _path("SLACK_MENTION_JEV_LOG", "~/.hermes/scripts/.slack-mention-jev.jsonl")
    for m in new:
        mkey = f"{m['channel_id']}:{m['ts']}"
        plain = " ".join(MARKUP_RE.sub(" ", m["text"] or "").split())
        t = threads[mkey] = thread(m, token, name)
        state = {"watched_user": f"@{name(uid)}", "mention": plain,
                 "thread": t if isinstance(t, str) else [line for _, line in t]}
        row = {"logged_at": time.time(), "key": mkey, "permalink": m["permalink"],
               "mention": plain, "regex_emoji": classify(m["text"]),
               "react_status": reacted.get(mkey), "jev_model": None, "p": None,
               "jev_emoji": None, "ms": 0, "error": None}
        t0 = time.monotonic()
        try:
            data = jev(state, key)
            raw = {k: float(data["answers"][k]["noul"]) for k in JEV_Q}
            row.update(jev_model=data.get("model"), p={k: round(v, 4) for k, v in raw.items()},
                       jev_emoji=jev_emoji(raw), ms=int((time.monotonic() - t0) * 1000))
            line = json.dumps(row, ensure_ascii=False, allow_nan=False)
        except Exception as e:
            code = getattr(e, "code", None) if isinstance(e, urllib.error.HTTPError) else None
            if code in (401, 403):
                print(f"{TAG} jev shadow: auth rejected (HTTP {code})", file=sys.stderr)
                return threads
            # Only the type name: str(e) can echo request headers, i.e. the key.
            row.update(jev_model=None, p=None, jev_emoji=None,
                       ms=int((time.monotonic() - t0) * 1000),
                       error=type(e).__name__ + (f" {code}" if code else ""))
            line = json.dumps(row, ensure_ascii=False)
        if dry_run:
            print(f"{TAG} {line}", file=sys.stderr)
            continue
        try:
            os.makedirs(os.path.dirname(log) or ".", exist_ok=True)
            with os.fdopen(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as f:
                f.write(line + "\n")
        except OSError as e:
            print(f"{TAG} jev shadow: log write failed: {type(e).__name__}", file=sys.stderr)
    return threads


def ignored_users(bot_tok):
    ids = {u.strip() for u in (env("SLACK_MENTION_IGNORE_USERS") or "").split(",") if u.strip()}
    if bot_tok:
        try:
            ids.add(api("auth.test", bot_tok)["user_id"])
        except SlackError:
            pass
    return ids


def config():
    uid = env("SLACK_MENTION_USER_ID")
    user_tok = env("SLACK_USER_READ_TOKEN")
    if not uid and user_tok:
        try:  # the user token's owner is the person to watch
            uid = api("auth.test", user_tok).get("user_id")
        except SlackError:
            pass
    uid = uid or (env("SLACK_ALLOWED_USERS") or "").split(",")[0].strip()
    if user_tok:
        return uid, "search", user_tok
    return uid, "history", env("SLACK_BOT_TOKEN")


def mentions(uid, mode, token, bot_tok, floor, recent=False):
    if mode == "search":
        found = search_mentions(token, uid, floor, *((100, 3) if recent else (50, 1)))
    else:
        found = history_mentions(token, uid, floor)
    if found:
        # Alerts are posted into SLACK_HOME_CHANNEL by the bot and quote the mention,
        # so search would return them as new mentions forever. Drop both ways.
        home, bots = env("SLACK_HOME_CHANNEL"), ignored_users(bot_tok)
        found = [m for m in found if m["channel_id"] != home and m["user"] not in bots]
    return found


def run(dry_run=False, as_digest=False, do_react=False):
    uid, mode, token = config()
    if not uid or not token:
        raise SlackError("missing SLACK_MENTION_USER_ID/SLACK_ALLOWED_USERS or token")
    bot_tok = env("SLACK_BOT_TOKEN")
    state_path = _path("SLACK_MENTION_STATE_FILE", "~/.hermes/scripts/.slack-mention-watch.json")
    state = load_state(state_path, float(env("SLACK_MENTION_LOOKBACK_MINS") or 60))
    started = time.time()
    floor = float(state["last_ts"]) - OVERLAP_SECS
    found = mentions(uid, mode, token, bot_tok, floor)
    seen = set(state["seen"])
    new = []
    for m in sorted(found, key=lambda m: float(m["ts"])):
        key = f"{m['channel_id']}:{m['ts']}"
        if key not in seen:
            seen.add(key)
            state["seen"].append(key)
            new.append(m)
    reacted = {}
    # history mode has no user token, so it can only read as the bot -- never react.
    if new and mode == "search" and react_enabled(do_react):
        reacted = react(new, env("SLACK_USER_REACT_TOKEN") or token, uid, dry_run)
    name = Names(bot_tok or token, uid)  # bot token has users:read; user token usually not
    threads = {}
    try:  # shadow mode is observation only: it must never cost a tick or its state
        threads = jev_shadow(new, token, uid, name, reacted, dry_run)
    except Exception as e:
        print(f"{TAG} jev shadow failed: {type(e).__name__}", file=sys.stderr)
    if as_digest:
        out = digest(new, name, token, uid, reacted, threads) if new else WAKE_FALSE
    else:
        out = "\n\n".join(fmt(m, name, token, reacted.get(f"{m['channel_id']}:{m['ts']}"))
                          for m in new)
    if not dry_run:
        state["last_ts"] = f"{max(started, float(state['last_ts'])):.6f}"
        state["seen"] = state["seen"][-SEEN_MAX:]
        save_state(state_path, state)
    return out


def recent(hours):
    """Every mention in the last `hours`, newest first. Never reads or writes state."""
    uid, mode, token = config()
    if not uid or not token:
        raise SlackError("missing SLACK_MENTION_USER_ID/SLACK_ALLOWED_USERS or token")
    bot_tok = env("SLACK_BOT_TOKEN")
    found = mentions(uid, mode, token, bot_tok, time.time() - hours * 3600, recent=True)
    uniq = {f"{m['channel_id']}:{m['ts']}": m for m in found}  # pages can overlap
    found = sorted(uniq.values(), key=lambda m: float(m["ts"]), reverse=True)[:RECENT_MAX]
    name = Names(bot_tok or token, uid)
    if not found:
        return f"No @{name(uid)} mentions in the last {hours:g} h."
    return "\n\n".join(fmt(m, name, token) for m in found)


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
    rtok, rscopes = env("SLACK_USER_REACT_TOKEN") or token, scopes
    if rtok != token:
        rhdrs = {}
        api("auth.test", rtok, _headers=rhdrs)
        rscopes = {k.lower(): v for k, v in rhdrs.items()}.get("x-oauth-scopes", "?")
    lines.append(f"react scope: {'yes' if 'reactions:write' in rscopes else 'no'}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="don't save state")
    ap.add_argument("--check", action="store_true", help="print diagnostics, no state")
    ap.add_argument("--recent", nargs="?", const=24.0, type=float, metavar="HOURS",
                    help="list all mentions in the last HOURS (default 24); no state")
    ap.add_argument("--digest", action="store_true",
                    help="new mentions + thread context for an LLM cron agent")
    ap.add_argument("--react", action="store_true",
                    help="add :eyes:/:raised_hands:/:memo: to new mentions (needs reactions:write)")
    a = ap.parse_args(argv)
    # A skipped tick must not wake the digest agent with empty context.
    skip = WAKE_FALSE if a.digest and not (a.check or a.recent is not None) else None
    try:
        if a.check:
            out = check()
        elif a.recent is not None:
            out = recent(a.recent)
        else:
            out = run(a.dry_run, a.digest, a.react)
    except RateLimited as e:
        print(f"{TAG} rate limited on {e}; skipping tick", file=sys.stderr)
        out = skip
    except urllib.error.URLError as e:
        # ponytail: network blips (laptop asleep, wifi) stay off stdout so cron doesn't spam.
        print(f"{TAG} network error: {e.reason}; skipping tick", file=sys.stderr)
        out = skip
    except SlackError as e:
        print(f"{TAG} ERROR: {e}")
        return 1
    if out:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
