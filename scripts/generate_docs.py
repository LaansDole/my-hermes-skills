#!/usr/bin/env python3
"""Generate docs/index.html from skills/**/SKILL.md frontmatter.

Zero dependencies (no PyYAML): parses the frontmatter subset used in this
repo — name, version, description (plain or double-quoted), tags (inline
list). Parent/child nesting is inferred from the folder tree: a SKILL.md
whose parent folder also contains a SKILL.md is a child of that skill.

Run:  python3 scripts/generate_docs.py
Out:  docs/index.html  (overwritten)
"""

import html
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"
OUT = REPO / "docs" / "index.html"
GH = "https://github.com/LaansDole/my-hermes-skills"

# top-level skills/ dir -> (section title, icon, icon bg color)
CATEGORY_MAP = {
    "covidence-screening":        ("Systematic Review (Covidence)", "🔬", "#1a2d4a"),
    "covidence-full-text-retrieval": ("Systematic Review (Covidence)", "🔬", "#1a2d4a"),
    "productivity":               ("Productivity", "⚡", "#2d1f4a"),
    "slack-scan":                 ("Slack", "💬", "#2d2a1f"),
}
# fixed section order; unknown sections append alphabetically
SECTION_ORDER = ["Systematic Review (Covidence)", "Productivity", "Slack"]


def parse_frontmatter(text: str) -> dict:
    """Extract name/version/description/tags from a SKILL.md frontmatter block."""
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}
    fm = m.group(1)
    out = {}

    name = re.search(r"^name:\s*(.+)$", fm, re.MULTILINE)
    if name:
        out["name"] = name.group(1).strip().strip('"')

    version = re.search(r"^version:\s*(.+)$", fm, re.MULTILINE)
    if version:
        out["version"] = version.group(1).strip().strip('"')

    desc = re.search(r"^description:\s*(.+)$", fm, re.MULTILINE)
    if desc:
        d = desc.group(1).strip()
        if d.startswith('"') and d.endswith('"'):
            d = d[1:-1].replace('\\"', '"')
        out["description"] = d

    tags = re.search(r"^\s*tags:\s*\[(.*?)\]", fm, re.MULTILINE)
    if tags:
        out["tags"] = [t.strip().strip('"').strip("'")
                       for t in tags.group(1).split(",") if t.strip()]
    return out


def find_skills() -> list:
    """Return dicts for every SKILL.md under skills/, with category/nesting."""
    skills = []
    for p in sorted(SKILLS.rglob("SKILL.md")):
        rel = p.relative_to(REPO)
        skill_dir = p.parent
        top = skill_dir.relative_to(SKILLS).parts[0]
        fm = parse_frontmatter(p.read_text())
        if not fm.get("name"):
            continue

        # child if the parent folder is itself a skill (has its own SKILL.md)
        parent_skill = None
        if (skill_dir.parent / "SKILL.md").exists():
            parent_skill = skill_dir.parent.name

        skills.append({
            "name": fm["name"],
            "version": fm.get("version", ""),
            "description": fm.get("description", ""),
            "tags": fm.get("tags", []),
            "rel_dir": str(skill_dir.relative_to(REPO)),
            "top": top,
            "parent_skill": parent_skill,
        })
    return skills


def card_html(s: dict, child: bool = False) -> str:
    cls = "card card-child" if child else "card"
    version = f'<span class="card-version">v{s["version"]}</span>' if s["version"] else ""
    tags = "\n".join(f'          <span class="tag">{html.escape(t)}</span>'
                     for t in s["tags"])
    desc = html.escape(s["description"])
    return f"""      <div class="{cls}">
        <div class="card-top">
          <span class="card-name">{html.escape(s['name'])}</span>
          {version}
          <div class="card-links">
            <a class="card-link" href="{GH}/blob/main/{s['rel_dir']}/SKILL.md" target="_blank">SKILL.md</a>
            <a class="card-link" href="{GH}/tree/main/{s['rel_dir']}" target="_blank">source</a>
          </div>
        </div>
        <p class="card-desc">
          {desc}
        </p>
        <div class="card-tags">
{tags}
        </div>
      </div>"""


def sections_html(skills: list) -> str:
    """Group skills by section title; children immediately after their parent."""
    by_section = {}
    for s in skills:
        title, icon, bg = CATEGORY_MAP.get(s["top"], (s["top"], "📦", "#21262d"))
        by_section.setdefault(title, {"icon": icon, "bg": bg, "skills": []})
        by_section[title]["skills"].append(s)

    ordered = sorted(by_section, key=lambda t: (SECTION_ORDER.index(t)
                                                if t in SECTION_ORDER
                                                else len(SECTION_ORDER) + 1))
    blocks = []
    for title in ordered:
        sec = by_section[title]
        cards = []
        for s in sorted(sec["skills"], key=lambda x: x["name"]):
            if s["parent_skill"]:
                continue  # rendered under its parent below
            cards.append(card_html(s))
            for c in sorted(sec["skills"], key=lambda x: x["name"]):
                if c["parent_skill"] == s["name"]:
                    cards.append(card_html(c, child=True))
        n = len(cards)
        count = "1 skill" if n == 1 else f"{n} skills"
        blocks.append(f"""  <!-- Category: {title} -->
  <div class="section">
    <div class="section-header">
      <div class="section-icon" style="background:{sec['bg']}">{sec['icon']}</div>
      <span class="section-title">{html.escape(title)}</span>
      <span class="section-count">{count}</span>
    </div>
    <div class="cards">

{chr(10).join(cards)}

    </div>
  </div>""")
    return "\n\n".join(blocks)


CSS = """    :root {
      --bg: #0d1117;
      --bg2: #161b22;
      --bg3: #21262d;
      --border: #30363d;
      --text: #e6edf3;
      --text-muted: #8b949e;
      --text-dim: #6e7681;
      --accent: #58a6ff;
      --accent-dim: #1f6feb;
      --green: #3fb950;
      --purple: #bc8cff;
      --orange: #d29922;
      --red: #f85149;
      --tag-bg: #1f2937;
      --tag-border: #374151;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      font-size: 14px;
      line-height: 1.6;
      min-height: 100vh;
    }

    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }

    /* Layout */
    header {
      background: var(--bg2);
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-inner {
      max-width: 960px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      gap: 16px;
      height: 56px;
    }
    .logo {
      display: flex;
      align-items: center;
      gap: 10px;
      font-weight: 600;
      font-size: 15px;
      color: var(--text);
    }
    .logo svg { flex-shrink: 0; }
    .header-links {
      margin-left: auto;
      display: flex;
      gap: 20px;
      font-size: 13px;
      color: var(--text-muted);
    }
    .header-links a { color: var(--text-muted); }
    .header-links a:hover { color: var(--text); text-decoration: none; }

    main {
      max-width: 960px;
      margin: 0 auto;
      padding: 48px 24px 80px;
    }

    /* Hero */
    .hero { margin-bottom: 48px; }
    .hero-eyebrow {
      font-size: 12px;
      font-family: var(--mono);
      color: var(--accent);
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .hero h1 {
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
      margin-bottom: 12px;
      background: linear-gradient(135deg, var(--text) 0%, var(--text-muted) 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }
    .hero-sub {
      color: var(--text-muted);
      font-size: 15px;
      max-width: 580px;
      margin-bottom: 24px;
    }
    .hero-stats { display: flex; gap: 24px; flex-wrap: wrap; }
    .stat { display: flex; flex-direction: column; gap: 2px; }
    .stat-num {
      font-size: 22px;
      font-weight: 700;
      color: var(--text);
      font-family: var(--mono);
    }
    .stat-label { font-size: 12px; color: var(--text-muted); }

    /* Section */
    .section { margin-bottom: 48px; }
    .section-header {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }
    .section-icon {
      width: 28px;
      height: 28px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 14px;
      flex-shrink: 0;
    }
    .section-title { font-size: 16px; font-weight: 600; color: var(--text); }
    .section-count {
      margin-left: auto;
      font-size: 12px;
      color: var(--text-dim);
      font-family: var(--mono);
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1px 8px;
    }

    /* Cards */
    .cards { display: flex; flex-direction: column; gap: 10px; }
    .card {
      background: var(--bg2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px 18px;
      transition: border-color 0.15s, background 0.15s;
      cursor: default;
    }
    .card:hover { border-color: var(--accent-dim); background: var(--bg3); }
    .card-top { display: flex; align-items: flex-start; gap: 12px; margin-bottom: 8px; }
    .card-name {
      font-family: var(--mono);
      font-size: 13px;
      font-weight: 600;
      color: var(--accent);
      flex: 1;
      min-width: 0;
    }
    .card-version {
      font-family: var(--mono);
      font-size: 11px;
      color: var(--text-dim);
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 1px 6px;
      flex-shrink: 0;
    }
    .card-links { display: flex; gap: 8px; flex-shrink: 0; }
    .card-link {
      font-size: 11px;
      color: var(--text-muted);
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 2px 8px;
      transition: color 0.15s, border-color 0.15s;
    }
    .card-link:hover { color: var(--text); border-color: var(--text-muted); text-decoration: none; }
    .card-desc {
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.55;
      margin-bottom: 10px;
    }
    .card-tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .tag {
      font-size: 11px;
      font-family: var(--mono);
      color: var(--text-dim);
      background: var(--tag-bg);
      border: 1px solid var(--tag-border);
      border-radius: 3px;
      padding: 1px 6px;
    }

    /* child card (indented) */
    .card-child {
      margin-left: 24px;
      border-left: 2px solid var(--border);
      border-radius: 0 8px 8px 0;
    }
    .card-child .card-name::before { content: "↳ "; color: var(--text-dim); }

    /* Setup box */
    .setup-box {
      background: var(--bg2);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 48px;
    }
    .setup-box h2 {
      font-size: 11px;
      font-weight: 600;
      margin-bottom: 12px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    .setup-step { display: flex; gap: 12px; margin-bottom: 10px; align-items: flex-start; }
    .step-num {
      width: 20px;
      height: 20px;
      border-radius: 50%;
      background: var(--accent-dim);
      color: var(--text);
      font-size: 11px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      margin-top: 1px;
    }
    .step-body { font-size: 13px; color: var(--text-muted); }
    .step-body code {
      font-family: var(--mono);
      font-size: 12px;
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 4px;
      padding: 1px 5px;
      color: var(--green);
    }

    /* Footer */
    footer {
      border-top: 1px solid var(--border);
      padding: 24px;
      text-align: center;
      color: var(--text-dim);
      font-size: 12px;
    }
    footer a { color: var(--text-dim); }
    footer a:hover { color: var(--text-muted); }

    @media (max-width: 600px) {
      .hero h1 { font-size: 24px; }
      .hero-stats { gap: 16px; }
      .card-child { margin-left: 12px; }
    }"""


def main() -> int:
    skills = find_skills()
    if not skills:
        print("error: no skills found under skills/", file=sys.stderr)
        return 1

    n_cats = len({CATEGORY_MAP.get(s["top"], (s["top"],))[0] for s in skills})
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>my-hermes-skills — LaansDole</title>
  <link rel="canonical" href="https://laansdole.github.io/my-hermes-skills/" />
  <style>
{CSS}
  </style>
</head>
<body>

<header>
  <div class="header-inner">
    <div class="logo">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="5" fill="#1f6feb"/>
        <path d="M5 14V6l5 4 5-4v8" stroke="#e6edf3" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      my-hermes-skills
    </div>
    <div class="header-links">
      <a href="{GH}" target="_blank">GitHub</a>
      <a href="https://hermes-agent.nousresearch.com/docs" target="_blank">Hermes Docs</a>
    </div>
  </div>
</header>

<main>

  <!-- Hero -->
  <div class="hero">
    <div class="hero-eyebrow">LaansDole / my-hermes-skills</div>
    <h1>Personal Hermes Agent Skills</h1>
    <p class="hero-sub">
      A curated collection of reusable skills for
      <a href="https://hermes-agent.nousresearch.com" target="_blank">Hermes Agent</a>
      — covering systematic review automation, productivity utilities, and Slack tooling.
      Each skill is self-contained with its own <code style="font-family:var(--mono);font-size:13px;color:var(--green);background:var(--bg3);border:1px solid var(--border);border-radius:4px;padding:1px 5px">SKILL.md</code> and setup instructions.
    </p>
    <div class="hero-stats">
      <div class="stat">
        <span class="stat-num">{len(skills)}</span>
        <span class="stat-label">skills</span>
      </div>
      <div class="stat">
        <span class="stat-num">{n_cats}</span>
        <span class="stat-label">categories</span>
      </div>
      <div class="stat">
        <span class="stat-num">MIT</span>
        <span class="stat-label">license</span>
      </div>
    </div>
  </div>

  <!-- Quick setup -->
  <div class="setup-box">
    <h2>Quick Setup</h2>
    <div class="setup-step">
      <div class="step-num">1</div>
      <div class="step-body">Clone or fork this repo, then symlink (or copy) any skill folder into <code>~/.hermes/skills/</code></div>
    </div>
    <div class="setup-step">
      <div class="step-num">2</div>
      <div class="step-body">Merge <code>.hermes-config/config-patch.yaml</code> into <code>~/.hermes/config.yaml</code> for auto-approvals needed by CDP browser skills</div>
    </div>
    <div class="setup-step">
      <div class="step-num">3</div>
      <div class="step-body">For skills with a <code>SETUP.md</code>, follow the per-skill setup steps (env vars, browser profiles, criteria files)</div>
    </div>
    <div class="setup-step">
      <div class="step-num">4</div>
      <div class="step-body">Hermes auto-discovers skills in <code>~/.hermes/skills/</code> — just start a new session and the skill will be available</div>
    </div>
  </div>

{sections_html(skills)}

</main>

<footer>
  <p>
    Built with <a href="https://hermes-agent.nousresearch.com" target="_blank">Hermes Agent</a> by Nous Research &nbsp;·&nbsp;
    <a href="{GH}/blob/main/LICENSE" target="_blank">MIT License</a> &nbsp;·&nbsp;
    <a href="{GH}" target="_blank">LaansDole/my-hermes-skills</a> &nbsp;·&nbsp;
    <a href="https://laansdole.github.io/my-hermes-skills/">laansdole.github.io/my-hermes-skills</a>
  </p>
</footer>

</body>
</html>
"""
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(skills)} skills, {n_cats} categories)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
