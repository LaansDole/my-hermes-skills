#!/usr/bin/env python3
"""Jira TODO digest for a Hermes cron job.

Pulls issues assigned to the current user via the Jira Cloud REST API,
filters to those with new activity since the last run, and prints them as
plain text so the Hermes cron agent can summarize + extract action items.
State (last-seen "updated" timestamp) is persisted in
~/.hermes/scripts/.jira-state.json.

Unlike slack-digest.py, missing configuration is NOT a hard error: if Jira
isn't set up yet, this prints an informative NO_CHANGE so the cron job
stays silent instead of breaking.

Env vars:
  JIRA_BASE_URL     https://yourcompany.atlassian.net  (required)
  JIRA_EMAIL        Atlassian account email             (required)
  JIRA_API_TOKEN    API token from id.atlassian.com/manage-profile/security/api-tokens (required)
  JIRA_JQL          base JQL filter, without the updated-since clause
                     (default: 'assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC')
  JIRA_LOOKBACK_MINS  if no state exists yet, treat issues updated within this
                     many minutes as new (default 1440 = 24h)
  JIRA_MAX_RESULTS  max issues to fetch per run (default 50)

Run standalone to test:
  JIRA_BASE_URL=https://x.atlassian.net JIRA_EMAIL=me@x.com JIRA_API_TOKEN=... python3 jira-digest.py
"""
import base64
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

STATE_FILE = os.path.expanduser("~/.hermes/scripts/.jira-state.json")
DEFAULT_JQL = 'assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC'


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


def parse_iso(ts):
    """Parse a Jira/ISO 8601 timestamp; return None on failure (treat as new)."""
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def api_get(url, email, token):
    auth = base64.b64encode(f"{email}:{token}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")

    if not base_url or not email or not token:
        print("[jira-digest] Jira is not configured (JIRA_BASE_URL / JIRA_EMAIL / JIRA_API_TOKEN missing).")
        print("Set these in ~/.hermes/.env to enable the Jira digest. See slack-todo-bot/.env.example.")
        print("NO_CHANGE")
        return

    jql = os.environ.get("JIRA_JQL", DEFAULT_JQL)
    max_results = int(os.environ.get("JIRA_MAX_RESULTS", "50"))
    lookback_mins = int(os.environ.get("JIRA_LOOKBACK_MINS", "1440"))

    fields = "summary,status,updated,issuetype,priority"
    qs = urllib.parse.urlencode({"jql": jql, "fields": fields, "maxResults": max_results})
    url = f"{base_url}/rest/api/3/search?{qs}"

    try:
        data = api_get(url, email, token)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        print(f"[jira-digest] Jira API error {e.code}: {body}")
        print("NO_CHANGE")
        return
    except urllib.error.URLError as e:
        print(f"[jira-digest] HTTP error calling Jira: {e}")
        print("NO_CHANGE")
        return

    state = load_state()
    last_seen = parse_iso(state.get("last_seen"))
    if last_seen is None:
        last_seen = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=lookback_mins)

    new_items = []
    max_updated = last_seen
    for issue in data.get("issues", []):
        f = issue.get("fields", {})
        updated = parse_iso(f.get("updated"))
        # Unparseable timestamp -> treat as new rather than silently dropping it.
        if updated is not None and updated <= last_seen:
            continue
        if updated is not None and updated > max_updated:
            max_updated = updated
        new_items.append(
            {
                "key": issue.get("key", "?"),
                "summary": (f.get("summary") or "").strip(),
                "status": (f.get("status") or {}).get("name", "?"),
                "type": (f.get("issuetype") or {}).get("name", "?"),
                "priority": (f.get("priority") or {}).get("name", ""),
                "url": f"{base_url}/browse/{issue.get('key', '')}",
            }
        )

    state["last_seen"] = max_updated.isoformat()
    save_state(state)

    if not new_items:
        print("NO_CHANGE")
        return

    print(f"NEW_JIRA_ACTIVITY ({len(new_items)} issue(s) with new activity):")
    print()
    for it in new_items:
        prio = f", {it['priority']}" if it["priority"] else ""
        print(f"- [{it['key']}] ({it['type']}, {it['status']}{prio}) {it['summary']}")
        print(f"  {it['url']}")


if __name__ == "__main__":
    main()
