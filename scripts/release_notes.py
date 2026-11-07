#!/usr/bin/env python3
"""Print GitHub release notes for skills whose SKILL.md `version:` changed since <base>.

Usage: release_notes.py <base-git-ref>

Each bumped (or new) versioned skill must have a `## [<version>]` section in
its CHANGELOG.md; that section becomes the skill's notes. Missing section ->
exit 1. No bumps -> prints nothing.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("generate_docs", REPO / "scripts" / "generate_docs.py")
gd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gd)


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, check=True,
                          capture_output=True, text=True).stdout


def base_versions(base: str) -> dict:
    """skill dir (repo-relative) -> version at <base>."""
    out = {}
    for path in git("ls-tree", "-r", "--name-only", base, "--", "skills").splitlines():
        if path.endswith("/SKILL.md"):
            out[str(Path(path).parent)] = gd.parse_frontmatter(git("show", f"{base}:{path}")).get("version", "")
    return out


def changelog_section(text: str, version: str):
    """Body of `## [version]` up to the next `## ` heading, or None."""
    m = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else None


def bumped(old: dict, new: dict) -> list:
    """Dirs whose version is set and differs from <base> (new skills included)."""
    return sorted(d for d, v in new.items() if v and old.get(d) != v)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    old = base_versions(sys.argv[1])
    skills = {s["rel_dir"]: s for s in gd.find_skills()}
    notes, missing = [], []
    for d in bumped(old, {d: s["version"] for d, s in skills.items()}):
        s = skills[d]
        cl = REPO / d / "CHANGELOG.md"
        body = changelog_section(cl.read_text(), s["version"]) if cl.exists() else None
        if not body:
            missing.append(f"{d}/CHANGELOG.md: no '## [{s['version']}]' section")
            continue
        notes.append(f"## {s['name']} v{s['version']}\n\n{body}\n")
    if missing:
        print("error: version bumped without changelog entry:\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1
    print("\n".join(notes), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
