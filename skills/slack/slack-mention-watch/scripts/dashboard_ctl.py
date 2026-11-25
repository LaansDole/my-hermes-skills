#!/usr/bin/env python3
"""Start / stop / status for the slack-mention-watch dashboard as a detached background server.

Built for one-shot callers (a Hermes quick command, a Slack request, cron): `start` returns at
once, the server keeps running after the caller exits. Idempotent: a running dashboard is reused.

    dashboard_ctl.py start [--port 8090] [--open]
    dashboard_ctl.py status
    dashboard_ctl.py stop
"""
import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
DASHBOARD = os.path.join(HERE, "dashboard.py")
HOME = os.path.expanduser(os.environ.get("HERMES_HOME", "~/.hermes"))
STATE = os.path.join(HOME, "scripts", ".slack-dashboard.json")
LOG = os.path.join(HOME, "logs", "slack-dashboard.log")


def listening(port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def is_dashboard(port):
    """True if the server on this port answers like our dashboard."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as r:
            return b"Slack mention watch" in r.read(4096)
    except Exception:
        return False


def pid_alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (OSError, TypeError):
        return False


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {}


def save(d):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    with open(STATE, "w") as f:
        json.dump(d, f)
    os.chmod(STATE, 0o600)


def start(port, open_browser):
    url = f"http://127.0.0.1:{port}"
    if listening(port):
        if not is_dashboard(port):
            print(f"ERROR: port {port} is in use by something else; try --port {port + 1}")
            return 1
        print(f"slack-mention dashboard already running: {url}")
    else:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        log = open(LOG, "ab")
        p = subprocess.Popen([sys.executable, DASHBOARD, "--port", str(port)],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                             start_new_session=True, close_fds=True)
        for _ in range(50):
            if listening(port):
                break
            if p.poll() is not None:
                print(f"ERROR: dashboard exited with {p.returncode}; see {LOG}")
                return 1
            time.sleep(0.1)
        else:
            print(f"ERROR: dashboard did not start listening on {port} in 5 s; see {LOG}")
            return 1
        save({"pid": p.pid, "port": port, "started": time.strftime("%Y-%m-%d %H:%M:%S")})
        print(f"slack-mention dashboard started: {url} (pid {p.pid}, log {LOG})")
    print("Loopback only: open it on this Mac.")
    if open_browser:
        webbrowser.open(url)
    return 0


def status(port):
    st = load()
    port = st.get("port", port)
    if listening(port) and is_dashboard(port):
        pid = st.get("pid")
        extra = f" (pid {pid}, since {st.get('started')})" if pid_alive(pid) else ""
        print(f"slack-mention dashboard running: http://127.0.0.1:{port}{extra}")
        return 0
    print("slack-mention dashboard not running")
    return 3


def stop(port):
    st = load()
    pid = st.get("pid")
    if isinstance(pid, int) and pid_alive(pid):
        os.kill(pid, signal.SIGTERM)
        for _ in range(30):
            if not pid_alive(pid):
                break
            time.sleep(0.1)
        try:
            os.remove(STATE)
        except OSError:
            pass
        print(f"slack-mention dashboard stopped (pid {pid})")
        return 0
    if listening(st.get("port", port)) and is_dashboard(st.get("port", port)):
        print("dashboard is running but was not started by dashboard_ctl.py (no pid); "
              "stop it where it was started")
        return 1
    print("slack-mention dashboard not running")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Start/stop/status the slack-mention dashboard in the background.")
    ap.add_argument("action", nargs="?", default="start", choices=["start", "status", "stop"])
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--open", action="store_true", help="also open the page in the browser")
    a = ap.parse_args(argv)
    return {"start": lambda: start(a.port, a.open), "status": lambda: status(a.port),
            "stop": lambda: stop(a.port)}[a.action]()


if __name__ == "__main__":
    sys.exit(main())
