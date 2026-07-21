#!/usr/bin/env python3
"""Slack notification digest for a Hermes cron job.

Reads new messages from one or more Slack channels (since the last run) via the
Slack Web API and prints them as plain text so the Hermes cron agent can
summarize them. State (last-read timestamp per channel) is persisted in
~/.hermes/scripts/.slack-state.json.

Env vars:
  SLACK_BOT_TOKEN      xoxb-...  (required)
  SLACK_WATCH_CHANNELS comma-separated channel IDs (default: SLACK_HOME_CHANNEL)
  SLACK_HOME_CHANNEL   fallback single channel ID
  SLACK_LOOKBACK_MINS  if no state exists yet, read this many minutes back (default 60)

Run standalone to test:
  SLACK_BOT_TOKEN=xoxb-... SLACK_WATCH_CHANNELS=C0123, C0456 python3 slack-digest.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STATE_FILE = os.path.expanduser("~/.hermes/scripts/.slack-state.json")
API = "https://slack.com/api"


def die(msg, code=1):
    print(f"[slack-digest] ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def api_get(method, params, token):
    qs = urllib.parse.urlencode(params)
    url = f"{API}/{method}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        die(f"HTTP error calling {method}: {e}")
    if not data.get("ok"):
        die(f"Slack API {method} returned error: {data.get('error', 'unknown')}")
    return data


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_FILE)
    try:
        os.chmod(STATE_FILE, 0o600)
    except OSError:
        pass


def fetch_new_messages(token, channel_id, oldest_ts):
    """Return list of (ts, user, text) for messages newer than oldest_ts."""
    msgs = []
    cursor = None
    # Cap pages to avoid runaway reads on the first run.
    for _ in range(5):
        params = {"channel": channel_id, "limit": 100, "oldest": oldest_ts}
        if cursor:
            params["cursor"] = cursor
        data = api_get("conversations.history", params, token)
        for m in data.get("messages", []):
            # Skip messages the bot itself posted (subtype bot_message) to
            # avoid echoing our own digests back.
            if m.get("subtype") == "bot_message":
                continue
            msgs.append((float(m.get("ts", "0")), m.get("user", "unknown"), m.get("text", "")))
        cursor = (data.get("response_metadata") or {}).get("next_cursor")
        if not cursor:
            break
    # Slack returns newest-first; flip to chronological.
    msgs.sort(key=lambda x: x[0])
    return msgs


def main():
    token = os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        die("SLACK_BOT_TOKEN is not set")

    channels_raw = os.environ.get("SLACK_WATCH_CHANNELS") or os.environ.get("SLACK_HOME_CHANNEL")
    if not channels_raw:
        die("SLACK_WATCH_CHANNELS or SLACK_HOME_CHANNEL is not set")

    channels = [c.strip() for c in channels_raw.split(",") if c.strip()]
    if not channels:
        die("no channel IDs resolved")

    lookback_mins = int(os.environ.get("SLACK_LOOKBACK_MINS", "60"))
    default_oldest = str(time.time() - lookback_mins * 60)

    state = load_state()
    total_new = 0
    out_lines = []

    for channel_id in channels:
        oldest_ts = state.get(channel_id, default_oldest)
        msgs = fetch_new_messages(token, channel_id, oldest_ts)
        if not msgs:
            continue
        latest_ts = max(ts for ts, _, _ in msgs)
        state[channel_id] = str(latest_ts)
        total_new += len(msgs)
        out_lines.append(f"### Channel {channel_id} ({len(msgs)} new message(s))")
        for ts, user, text in msgs:
            text = (text or "").replace("\n", " ").strip()
            if len(text) > 500:
                text = text[:497] + "..."
            out_lines.append(f"- [{ts}] <{user}> {text}")
        out_lines.append("")

    save_state(state)

    if total_new == 0:
        print("NO_CHANGE")
        return

    print(f"NEW_SLACK_ACTIVITY ({total_new} new message(s) across {len(channels)} channel(s)):")
    print()
    print("\n".join(out_lines))


if __name__ == "__main__":
    main()
