#!/usr/bin/env python3
"""Tests for skills/slack/slack-mention-watch/scripts/dashboard_ctl.py (real local server, temp HERMES_HOME).

Run:  python3 -m unittest -v tests.test_dashboard_ctl
"""

import os
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CTL = Path(__file__).resolve().parent.parent / "skills/slack/slack-mention-watch/scripts/dashboard_ctl.py"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class DashboardCtlTest(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.home, "cron"))
        self.env = dict(os.environ, HERMES_HOME=self.home)
        self.port = str(free_port())

    def run_ctl(self, *args):
        return subprocess.run([sys.executable, str(CTL), *args, "--port", self.port],
                              env=self.env, capture_output=True, text=True, timeout=30)

    def tearDown(self):
        self.run_ctl("stop")

    def test_lifecycle(self):
        self.assertEqual(self.run_ctl("status").returncode, 3)
        r = self.run_ctl("start")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("started: http://127.0.0.1:" + self.port, r.stdout)
        r = self.run_ctl("start")  # idempotent
        self.assertIn("already running", r.stdout)
        self.assertEqual(self.run_ctl("status").returncode, 0)
        r = self.run_ctl("stop")
        self.assertIn("stopped", r.stdout)
        self.assertEqual(self.run_ctl("status").returncode, 3)

    def test_foreign_port_refused(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", int(self.port)))
            s.listen()
            r = self.run_ctl("start")
        self.assertEqual(r.returncode, 1)
        self.assertIn("in use by something else", r.stdout)


if __name__ == "__main__":
    unittest.main()
