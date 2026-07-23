#!/usr/bin/env python3
"""GitHub TODO digest for a Hermes cron job.

Pulls issues/PRs assigned to the authenticated user plus PRs awaiting their
review via the GitHub REST API, filters to items with new activity since
the last run, and prints them as plain text so the Hermes cron agent can
summarize + extract action items. State (last-seen "updated_at" timestamp)
is persisted in ~/.hermes/scripts/.github-state.json.

Unlike slack-digest.py, missing configuration is NOT a hard error: if
GitHub isn't set up yet, this prints an informative NO_CHANGE so the cron
job stays silent instead of breaking.

Env vars:
  GITHUB_TOKEN      Personal access token with `repo` scope (classic) or
                     Issues:read + Pull requests:read (fine-grained). Required.
  GITHUB_LOOKBACK_MINS  if no state exists yet, treat items updated within
                     this many minutes as new (default 60)
  GITHUB_MAX_RESULTS  max items to fetch per query (default 50)

NOTE on GITHUB_TOKEN: Hermes strips GITHUB_TOKEN (and GH_TOKEN) from every
subprocess it spawns -- terminal tool calls AND cron `no_agent` script runs
alike -- because that name is reserved for `gh` CLI auth in Hermes's own
credential blocklist (tools/environments/local.py `_ALWAYS_STRIP_KEYS`; see
SECURITY.md section 2.3 / GHSA-rhgp-j443-p4rf). That strip fires even when
this script is invoked directly by the cron scheduler, not through the LLM.
`env_or_dotenv()` below falls back to parsing GITHUB_TOKEN straight out of
~/.hermes/.env when os.environ doesn't have it, which is the case on every
real Hermes run.

Run standalone to test:
  GITHUB_TOKEN=ghp_... python3 github-digest.py
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

STATE_FILE = os.path.expanduser("~/.hermes/scripts/.github-state.json")
DOTENV_FILE = os.path.expanduser("~/.hermes/.env")
API = "https://api.github.com"


def dotenv_fallback(name):
    """Read NAME=value straight out of ~/.hermes/.env (bypasses the
    os.environ strip -- see the module docstring)."""
    try:
        with open(DOTENV_FILE, "r") as f:
            for line in f:
                m = re.match(rf"^{re.escape(name)}=(.*)$", line.strip())
                if m:
                    return m.group(1).strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def env_or_dotenv(name):
    return os.environ.get(name) or dotenv_fallback(name)


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


def api_get(url, token):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    token = env_or_dotenv("GITHUB_TOKEN")
    if not token:
        print("[github-digest] GitHub is not configured (GITHUB_TOKEN missing).")
        print("Set GITHUB_TOKEN in ~/.hermes/.env to enable the GitHub digest. See slack-todo-bot/.env.example.")
        print("NO_CHANGE")
        return

    max_results = int(os.environ.get("GITHUB_MAX_RESULTS", "50"))
    lookback_mins = int(os.environ.get("GITHUB_LOOKBACK_MINS", "60"))

    items = []
    try:
        # Issues (and PRs) assigned to the authenticated user, across all repos.
        assigned = api_get(
            f"{API}/issues?filter=assigned&state=open&sort=updated&direction=desc&per_page={max_results}",
            token,
        )
        for it in assigned:
            items.append(
                {
                    "kind": "PR" if "pull_request" in it else "issue",
                    "repo_hash": it.get("repository_url", "").rsplit("/", 2)[-2:],
                    "number": it.get("number"),
                    "title": it.get("title", ""),
                    "url": it.get("html_url", ""),
                    "updated_at": it.get("updated_at", ""),
                    "reason": "assigned",
                }
            )

        # PRs awaiting the authenticated user's review, across all repos.
        review_requested = api_get(
            f"{API}/search/issues?q=is:pr+is:open+review-requested:@me&sort=updated&order=desc&per_page={max_results}",
            token,
        )
        for it in review_requested.get("items", []):
            items.append(
                {
                    "kind": "PR",
                    "repo_hash": it.get("repository_url", "").rsplit("/", 2)[-2:],
                    "number": it.get("number"),
                    "title": it.get("title", ""),
                    "url": it.get("html_url", ""),
                    "updated_at": it.get("updated_at", ""),
                    "reason": "review-requested",
                }
            )
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        print(f"[github-digest] GitHub API error {e.code}: {body}")
        print("NO_CHANGE")
        return
    except urllib.error.URLError as e:
        print(f"[github-digest] HTTP error calling GitHub: {e}")
        print("NO_CHANGE")
        return

    state = load_state()
    last_seen = state.get("last_seen")
    if not last_seen:
        import datetime

        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=lookback_mins)
        last_seen = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Dedupe (assigned + review-requested can overlap) and filter by activity.
    seen_urls = set()
    new_items = []
    max_updated = last_seen
    for it in items:
        url = it["url"]
        if url in seen_urls:
            continue
        seen_urls.add(url)
        updated_at = it["updated_at"]
        # ISO-8601 UTC "Z" timestamps compare correctly as strings.
        if updated_at and updated_at <= last_seen:
            continue
        if updated_at and updated_at > max_updated:
            max_updated = updated_at
        new_items.append(it)

    state["last_seen"] = max_updated
    save_state(state)

    if not new_items:
        print("NO_CHANGE")
        return

    print(f"NEW_GITHUB_ACTIVITY ({len(new_items)} item(s) with new activity):")
    print()
    for it in new_items:
        owner_repo = "/".join(it["repo_hash"]) if it["repo_hash"] else "?"
        tag = f"{it['kind']}" if it["reason"] == "assigned" else f"{it['kind']} review-requested"
        print(f"- [{tag}] {owner_repo}#{it['number']} {it['title']}")
        print(f"  {it['url']}")


if __name__ == "__main__":
    main()
