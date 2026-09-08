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
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKILLS = REPO / "skills"
REPORTS = REPO / "reports"
OUT = REPO / "docs" / "index.html"
GH = "https://github.com/LaansDole/my-hermes-skills"

# top-level skills/ dir -> (section title, icon, icon bg color)
CATEGORY_MAP = {
    "covidence-screening":        ("Research", "🔬", "#1a2d4a"),
    "covidence-full-text-retrieval": ("Research", "🔬", "#1a2d4a"),
    "productivity":               ("Productivity", "⚡", "#2d1f4a"),
    "sci-hub-access":             ("Research", "📚", "#1f4a2d"),
    "slack-scan":                 ("Slack", "💬", "#2d2a1f"),
    "oh-my-pi":                   ("Coding Agents", "🤖", "#0f3a3a"),
}
# fixed section order; unknown sections append alphabetically
SECTION_ORDER = ["Research", "Productivity", "Coding Agents", "Slack"]


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
        elif d.startswith("'") and d.endswith("'"):
            d = d[1:-1].replace("\\'", "'")
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


def find_reports() -> list:
    """Return dicts for every report markdown file under reports/YYYY-MM/.

    Expected naming: YYYY-MM-DD-<slug>.md; the leading date becomes the card
    date and the slug becomes the title. Files not matching the pattern still
    render, keyed by filename.
    """
    reports = []
    if not REPORTS.is_dir():
        return reports
    for p in sorted(REPORTS.rglob("*.md"), reverse=True):
        rel = p.relative_to(REPO)
        stem = p.stem
        m = re.match(r"^(\d{4}-\d{2}-\d{2})-(.+)$", stem)
        date, slug = (m.group(1), m.group(2)) if m else ("", stem)
        # Human title from slug: first paragraph of the file is the fallback.
        title = slug.replace("-", " ").replace("_", " ").strip()
        text = p.read_text()
        h1 = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        if h1:
            title = h1.group(1).strip()
        # Verdict = first non-empty line after a '## Verdict' heading, if any.
        verdict = ""
        vm = re.search(r"^##\s+Verdict\s*$\n+(.+)$", text, re.MULTILINE)
        if vm:
            verdict = vm.group(1).strip().split("\n")[0]
        reports.append({
            "rel_path": str(rel),
            "date": date,
            "title": title,
            "verdict": verdict,
        })
    return reports


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


def inline_md(text: str) -> str:
    """Render inline markdown (bold/italic/code/links) to HTML."""
    s = html.escape(text, quote=False)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


def report_card_html(r: dict) -> str:
    """One report card for the Daily News page. The WHOLE card links to the
    rendered report page (no separate button)."""
    date = html.escape(r["date"]) if r["date"] else "undated"
    title_html = inline_md(r["title"])
    verdict = ""
    if r["verdict"]:
        verdict = f"""\n          <p class=\"card-desc\">\n            <strong style=\"color:var(--green)\">Verdict:</strong> {inline_md(r['verdict'][:280])}\n          </p>"""
    # Site root = docs/ => site path /my-hermes-skills/... Use repo-relative
    # links WITHOUT ".." so the project-site base path is never escaped.
    page_href = "reports/" + r["rel_path"][len("reports/"):-3] + ".html"
    return f"""      <a class="card card-report" href="{page_href}">
        <div class="card-top">
          <span class="card-name">{title_html}</span>
          <span class="card-version">{date}</span>
        </div>{verdict}
      </a>"""


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


def entry_json(s: dict, title: str) -> dict:
    """One flat manifest entry for a skill."""
    return {
        "name": s["name"],
        "version": s["version"],
        "description": s["description"],
        "category": title,
        "path": s["rel_dir"],
        "url": f"{GH}/tree/main/{s['rel_dir']}",
    }


def manifest_json(skills: list) -> dict:
    """Build the skills.json manifest (deterministic: no timestamps)."""
    flat = []
    by_section = {}
    for s in sorted(skills, key=lambda x: x["name"]):
        title, _, _ = CATEGORY_MAP.get(s["top"], (s["top"], "📦", "#21262d"))
        flat.append(entry_json(s, title))
        by_section.setdefault(title, []).append(s)

    ordered = sorted(by_section, key=lambda t: (SECTION_ORDER.index(t)
                                                if t in SECTION_ORDER
                                                else len(SECTION_ORDER) + 1))
    sections = []
    for title in ordered:
        sec_skills = []
        for s in sorted(by_section[title], key=lambda x: x["name"]):
            if s["parent_skill"]:
                continue  # rendered under its parent below
            sec_skills.append(entry_json(s, title))
            for c in sorted(by_section[title], key=lambda x: x["name"]):
                if c["parent_skill"] == s["name"]:
                    sec_skills.append(entry_json(c, title))
        sections.append({"title": title, "skills": sec_skills})

    return {
        "source_repo": GH,
        "skills": flat,
        "sections": sections,
    }


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

    /* Light theme (GitHub light palette) — applied via [data-theme] set by the
       inline JS (OS preference, overridable by the header toggle, persisted) */
    :root[data-theme="light"] {
      --bg: #ffffff;
      --bg2: #f6f8fa;
      --bg3: #eaeef2;
      --border: #d0d7de;
      --text: #1f2328;
      --text-muted: #59636e;
      --text-dim: #6e7781;
      --accent: #0969da;
      --accent-dim: #0969da;
      --green: #1a7f37;
      --purple: #8250df;
      --orange: #9a6700;
      --red: #cf222e;
      --tag-bg: #eff1f3;
      --tag-border: #d0d7de;
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
      align-items: center;
      gap: 20px;
      font-size: 13px;
      color: var(--text-muted);
    }
    .header-links a { color: var(--text-muted); }
    .header-links a:hover { color: var(--text); text-decoration: none; }

    .theme-toggle {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 28px;
      height: 28px;
      background: var(--bg3);
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 14px;
      line-height: 1;
      padding: 0;
      cursor: pointer;
      transition: color 0.15s, border-color 0.15s, background 0.15s;
    }
    .theme-toggle:hover { border-color: var(--text-muted); background: var(--bg3); }

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
    .card-name .card-title-link { color: inherit; text-decoration: none; }
    .card-name .card-title-link:hover { color: var(--text); text-decoration: underline; }
    .card-name .card-title-link strong { color: inherit; }
    /* whole-card link (Daily News report cards) */
    a.card { text-decoration: none; display: block; color: inherit; }
    a.card:hover { border-color: var(--accent); }
    a.card:hover .card-name { text-decoration: underline; }
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


# Set data-theme before first paint: stored choice wins, else follow the OS.
PREPAINT_JS = """  <script>
    (function () {
      var t = null;
      try { t = localStorage.getItem("theme"); } catch (e) {}
      if (!t) {
        var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)");
        t = m && m.matches ? "light" : "dark";
      }
      document.documentElement.setAttribute("data-theme", t);
    })();
  </script>"""

# Header toggle: flips the theme, persists the choice; auto-follows the OS
# until the user overrides it. Icon shows the theme you'll switch to.
TOGGLE_JS = """  <script>
    (function () {
      var root = document.documentElement;
      var btn = document.getElementById("theme-toggle");
      var icon = document.getElementById("theme-icon");
      var stored = null;
      try { stored = localStorage.getItem("theme"); } catch (e) {}
      if (!btn || !icon) return;
      function paint() {
        icon.textContent = root.getAttribute("data-theme") === "light" ? "🌙" : "☀️";
      }
      btn.addEventListener("click", function () {
        var next = root.getAttribute("data-theme") === "light" ? "dark" : "light";
        root.setAttribute("data-theme", next);
        try { localStorage.setItem("theme", next); } catch (e) {}
        paint();
      });
      paint();
      var m = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)");
      if (m && !stored) {
        m.addEventListener("change", function (e) {
          root.setAttribute("data-theme", e.matches ? "light" : "dark");
          paint();
        });
      }
    })();
  </script>"""


def md_to_html(text: str) -> str:
    """Minimal zero-dependency markdown -> HTML for report files.

    Handles the constructs the writing-reports template produces: headings,
    bold/italic/inline code, fenced code blocks, GFM tables, ordered and
    unordered lists, blockquotes, hr, and links. Escapes everything else.
    """
    # fenced code blocks first (protect from other passes)
    blocks: list[str] = []

    def _fence(m: re.Match) -> str:
        blocks.append(f"<pre><code>{html.escape(m.group(1))}</code></pre>")
        return f"\x00FENCE{len(blocks) - 1}\x00"

    text = re.sub(r"```[^\n]*\n(.*?)```", _fence, text, flags=re.S)

    # footnotes: [^n]: definitions are collected out of the flow, inline [^n]
    # markers become sup backlinks. The marker pass runs inside inline() so the
    # generated HTML is not escaped by the per-line/per-cell escaping there.
    fndefs: dict[str, str] = {}

    def _fndef(m: re.Match) -> str:
        fndefs[m.group(1)] = m.group(2).strip()
        return ""

    text = re.sub(r"^\[\^([a-z0-9]+)\]:\s*(.+)$", _fndef, text, flags=re.MULTILINE)
    fnseen: set[str] = set()

    def _fnref(m: re.Match) -> str:
        k = m.group(1)
        # only the first mention carries the id, so backlinks stay unique
        ref = "" if k in fnseen else f' id="fnref-{k}"'
        fnseen.add(k)
        return f'<sup class="fn"{ref}><a href="#fn-{k}">{k}</a></sup>'

    def inline(s: str) -> str:
        s = html.escape(s, quote=False)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        # markdown autolink <URL> -> anchor (before other substitutions)
        s = re.sub(r"&lt;(https?://[^&\s]+)&gt;",
                   rf'<a href="\1" target="_blank">\1</a>', s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)",
                   rf'<a href="\2" target="_blank">\1</a>', s)
        # autolink bare URLs not already inside an href
        s = re.sub(r'(?<!href=")(?<!">)(https?://[^\s<)"]+)',
                   rf'<a href="\1" target="_blank">\1</a>', s)
        s = re.sub(r"\[\^([a-z0-9]+)\]", _fnref, s)
        return s

    lines = text.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("\x00FENCE"):
            out.append(ln); i += 1; continue
        if re.match(r"^\s*(---+|\*\*\*+)\s*$", ln):
            out.append("<hr>"); i += 1; continue
        h = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if h:
            lvl = len(h.group(1))
            out.append(f"<h{lvl}>{inline(h.group(2))}</h{lvl}>"); i += 1; continue
        # table: header row then a |---| separator
        if "|" in ln and i + 1 < len(lines) and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1] or ""):
            rows = []
            header = [c.strip() for c in ln.strip().strip("|").split("|")]
            i += 2
            while i < len(lines) and "|" in lines[i] and lines[i].strip():
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            th = "".join(f"<th>{inline(c)}</th>" for c in header)
            out.append(f"<table><thead><tr>{th}</tr></thead><tbody>")
            for r in rows:
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>")
            out.append("</tbody></table>")
            continue
        m_ol = re.match(r"^\s*(\d+)\.\s+(.*)$", ln)
        if m_ol:
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                items.append(re.sub(r"^\s*\d+\.\s+", "", lines[i])); i += 1
            out.append("<ol>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ol>")
            continue
        m_ul = re.match(r"^\s*[-*]\s+(.*)$", ln)
        if m_ul:
            items = []
            while i < len(lines) and re.match(r"^\s*[-*]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*]\s+", "", lines[i])); i += 1
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            continue
        if ln.startswith(">"):
            quote = []
            while i < len(lines) and lines[i].startswith(">"):
                quote.append(lines[i].lstrip("> ").rstrip()); i += 1
            out.append(f"<blockquote>{inline(' '.join(quote))}</blockquote>")
            continue
        if ln.strip():
            para = [ln]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||\s*[-*]\s|\s*\d+\.\s|>|```|\s*---)", lines[i + 1]):
                i += 1; para.append(lines[i])
            out.append(f"<p>{inline(' '.join(p.strip() for p in para))}</p>")
        i += 1
    html_out = "\n".join(out)
    for n, b in enumerate(blocks):
        html_out = html_out.replace(f"\x00FENCE{n}\x00", b)
    if fndefs:
        items = "".join(
            f'<li id="fn-{k}">{inline(v)} <a href="#fnref-{k}">&#8617;</a></li>'
            for k, v in fndefs.items()
        )
        html_out += f'<section class="footnotes"><hr><ol>{items}</ol></section>'
    return html_out


def write_report_pages(reports: list) -> None:
    """Render each report markdown file as a styled HTML page under docs/reports/."""
    base = REPO / "docs" / "reports"
    for r in reports:
        src = REPO / r["rel_path"]
        rel_html = Path(r["rel_path"]).with_suffix(".html")
        dst = base / Path(*rel_html.parts[1:])  # strip leading reports/
        dst.parent.mkdir(parents=True, exist_ok=True)
        body = md_to_html(src.read_text())
        title = html.escape(r["title"])
        page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title} — Daily News</title>
  <style>
{REPORT_CSS}
  </style>
{PREPAINT_JS}
</head>
<body>

<header>
  <div class="header-inner">
    <div class="logo">
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect width="20" height="20" rx="5" fill="#1f6feb"/>
        <path d="M5 14V6l5 4 5-4v8" stroke="#e6edf3" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      Daily News
    </div>
    <div class="header-links">
      <a href="daily-news.html">All reports</a>
      <a href="{GH}/blob/main/{r['rel_path']}" target="_blank">Markdown source</a>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light/dark theme" title="Toggle light/dark theme"><span id="theme-icon">☀️</span></button>
    </div>
  </div>
</header>

<main>
  <article>
{body}
  </article>
</main>

<footer>
  <p>
    <a href="daily-news.html">← All reports</a> &nbsp;·&nbsp;
    Filed by the writing-reports skill &nbsp;·&nbsp;
    <a href="{GH}" target="_blank">LaansDole/my-hermes-skills</a>
  </p>
</footer>

{TOGGLE_JS}
</body>
</html>
"""
        dst.write_text(page)


REPORT_CSS = """
    :root { --bg:#0d1117; --bg2:#161b22; --border:#21262d; --text:#e6edf3;
            --text-muted:#8b949e; --text-dim:#6e7681; --accent:#1f6feb;
            --green:#3fb950; --mono:ui-monospace,SFMono-Regular,Menlo,monospace; }
    :root[data-theme="light"] { --bg:#ffffff; --bg2:#f6f8fa; --border:#d0d7de;
            --text:#1f2328; --text-muted:#656d76; --text-dim:#8c959f;
            --accent:#0969da; --green:#1a7f37; }
    * { box-sizing:border-box; }
    body { margin:0; background:var(--bg); color:var(--text);
           font:15px/1.7 -apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif; }
    header { border-bottom:1px solid var(--border); background:var(--bg); }
    .header-inner { max-width:860px; margin:0 auto; padding:12px 24px;
                    display:flex; justify-content:space-between; align-items:center; }
    .logo { display:flex; gap:8px; align-items:center; font-weight:600; font-size:14px; }
    .header-links { display:flex; gap:16px; align-items:center; }
    .header-links a { color:var(--text-muted); text-decoration:none; font-size:13px; }
    .header-links a:hover { color:var(--text); }
    .theme-toggle { background:none; border:1px solid var(--border); border-radius:6px;
                    padding:4px 8px; cursor:pointer; font-size:13px; }
    main { max-width:860px; margin:0 auto; padding:40px 24px 64px; }
    article h1 { font-size:28px; line-height:1.3; margin:0 0 20px; }
    article h2 { font-size:20px; margin:36px 0 12px; padding-bottom:6px;
                 border-bottom:1px solid var(--border); }
    article h3 { font-size:16px; margin:24px 0 8px; }
    article p, article li { color:var(--text); }
    article code { font-family:var(--mono); font-size:13px; background:var(--bg2);
                   border:1px solid var(--border); border-radius:4px; padding:1px 5px; }
    article pre { background:var(--bg2); border:1px solid var(--border); border-radius:8px;
                  padding:14px; overflow-x:auto; }
    article pre code { background:none; border:none; padding:0; }
    article table { border-collapse:collapse; width:100%; margin:16px 0; font-size:14px; }
    article th, article td { border:1px solid var(--border); padding:7px 10px; text-align:left; }
    article th { background:var(--bg2); font-weight:600; }
    article tr:nth-child(even) td { background:var(--bg2); }
    article blockquote { border-left:3px solid var(--accent); margin:16px 0; padding:4px 16px;
                         color:var(--text-muted); }
    article hr { border:none; border-top:1px solid var(--border); margin:28px 0; }
    article a { color:var(--accent); }
    article sup.fn a { text-decoration:none; color:var(--accent); font-size:11px; }
    article .footnotes { font-size:13px; color:var(--text-muted); }
    article .footnotes li { margin-bottom:6px; }
    footer { border-top:1px solid var(--border); padding:20px 24px; text-align:center;
             color:var(--text-dim); font-size:12px; }
    footer a { color:var(--text-dim); }
    footer a:hover { color:var(--text-muted); }
"""


def write_daily_news(reports: list) -> None:
    """Generate docs/daily-news.html — a dedicated tab page for dated reports."""
    out = REPO / "docs" / "daily-news.html"
    if not reports:
        cards = "    <p class=\"card-desc\" style=\"padding:0 4px\">No reports filed yet.</p>\n"
    else:
        cards = "\n".join(report_card_html(r) for r in reports)
    n = len(reports)
    count = "1 report" if n == 1 else f"{n} reports"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Daily News — my-hermes-skills</title>
  <link rel="canonical" href="https://laansdole.github.io/my-hermes-skills/daily-news.html" />
  <style>
{CSS}
  </style>
{PREPAINT_JS}
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
      <a href="index.html">Skills</a>
      <a href="{GH}" target="_blank">GitHub</a>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light/dark theme" title="Toggle light/dark theme"><span id="theme-icon">☀️</span></button>
    </div>
  </div>
</header>

<main>

  <div class="hero">
    <div class="hero-eyebrow">LaansDole / my-hermes-skills</div>
    <h1>Daily News</h1>
    <p class="hero-sub">
      Dated reports filed by the <a href="{GH}/blob/main/skills/productivity/writing-reports/SKILL.md" target="_blank">writing-reports</a> skill —
      one card per report, newest first. Each card links to the full markdown report in the repo.
    </p>
    <div class="hero-stats">
      <div class="stat">
        <span class="stat-num">{n}</span>
        <span class="stat-label">reports</span>
      </div>
      <div class="stat">
        <span class="stat-num">📅</span>
        <span class="stat-label">newest first</span>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-header">
      <div class="section-icon" style="background:#3a2a0f">📰</div>
      <span class="section-title">All reports</span>
      <span class="section-count">{count}</span>
    </div>
    <div class="cards">

{cards}

    </div>
  </div>

</main>

<footer>
  <p>
    Built with <a href="https://hermes-agent.nousresearch.com" target="_blank">Hermes Agent</a> by Nous Research &nbsp;·&nbsp;
    <a href="{GH}/blob/main/LICENSE" target="_blank">MIT License</a> &nbsp;·&nbsp;
    <a href="{GH}" target="_blank">LaansDole/my-hermes-skills</a> &nbsp;·&nbsp;
    <a href="index.html">Skills</a>
  </p>
</footer>

{TOGGLE_JS}
</body>
</html>
"""
    out.write_text(page)
    print(f"wrote {out} ({n} reports)")


def main() -> int:
    skills = find_skills()
    if not skills:
        print("error: no skills found under skills/", file=sys.stderr)
        return 1

    reports = find_reports()
    write_report_pages(reports)
    write_daily_news(reports)

    if "--json" in sys.argv:
        manifest = manifest_json(skills)
        json_out = REPO / "skills.json"
        json_out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {json_out} ({len(manifest['skills'])} skills)")
        return 0

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
{PREPAINT_JS}
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
      <a href="daily-news.html">Daily News</a>
      <a href="{GH}" target="_blank">GitHub</a>
      <a href="https://hermes-agent.nousresearch.com/docs" target="_blank">Hermes Docs</a>
      <button id="theme-toggle" class="theme-toggle" type="button" aria-label="Toggle light/dark theme" title="Toggle light/dark theme"><span id="theme-icon">☀️</span></button>
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
      <div class="step-body">For skills with a <code>README.md</code>, follow the per-skill setup steps (env vars, browser profiles, criteria files)</div>
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

{TOGGLE_JS}
</body>
</html>
"""
    OUT.write_text(page)
    print(f"wrote {OUT} ({len(skills)} skills, {n_cats} categories)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
