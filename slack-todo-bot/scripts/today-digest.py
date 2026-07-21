#!/usr/bin/env python3
"""Today TODO digest for a Hermes cron job.

Runs the `today` CLI (todo-today-cli) over a task directory and prints its
output so the Hermes cron agent can summarize what's due/overdue today and
flag carry-over work. Pure passthrough -- no transformation beyond a header.

Env vars:
  TODAY_DIR       directory containing Markdown task files (default: $HOME/tasks)
  TODAY_LOOKAHEAD days to look ahead (default: 0 = today only)

Requires `today` on PATH. Install with:
  uv tool install todo-today-cli
"""
import os
import shutil
import subprocess
import sys


def main():
    today_bin = shutil.which("today")
    if not today_bin:
        print("[today-digest] `today` CLI is not installed.")
        print("Install it with:  uv tool install todo-today-cli")
        print("NO_CHANGE")
        return

    task_dir = os.path.expanduser(os.environ.get("TODAY_DIR") or os.path.join(os.path.expanduser("~"), "tasks"))
    if not os.path.isdir(task_dir):
        print(f"[today-digest] task dir does not exist: {task_dir}")
        print("NO_CHANGE")
        return

    lookahead = os.environ.get("TODAY_LOOKAHEAD", "0")

    try:
        result = subprocess.run(
            [today_bin, "--dir", task_dir, "--days", str(lookahead)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        print("[today-digest] `today` CLI timed out after 60s")
        print("NO_CHANGE")
        return

    out = result.stdout.strip()
    err = result.stderr.strip()
    if not out and err:
        print(f"[today-digest] `today` produced only stderr:\n{err}")
        print("NO_CHANGE")
        return

    if not out:
        print("NO_CHANGE")
        return

    # `today` prints "Tasks for today (YYYY-MM-DD)" then a tree. Skip
    # NO_CHANGE entirely when there is real output.
    print("TODAY_TASKS:")
    print()
    print(out)


if __name__ == "__main__":
    main()
