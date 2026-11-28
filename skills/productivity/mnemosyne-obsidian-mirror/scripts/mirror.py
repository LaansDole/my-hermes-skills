#!/usr/bin/env python3
"""Mirror Mnemosyne memories into an Obsidian vault as categorised, read-only notes.

One-way: Mnemosyne (SQLite) -> markdown. Nothing is ever written to Mnemosyne.
The database is opened read-only (sqlite URI mode=ro).

Output (under <vault>/<folder>/, default "Hermes Memory"):
  Index.md            totals, links to every topic and type note
  Topics/<Topic>.md   memories of one topic, grouped by type
  Types/<Type>.md     memories of one type, grouped by topic

Every generated note carries `generated_by: mnemosyne-obsidian-mirror` in its
frontmatter. Only files carrying that marker are ever rewritten or deleted;
anything else in the folder is left alone.

Categorisation:
  type  - from the Mnemosyne `source` field (preference, fact, task, ...).
  topic - first matching rule in the rules JSON file (keywords and/or sources),
          else "General". See categories.example.json.

Usage:
  mirror.py                 write/refresh the notes (prints one line if anything changed)
  mirror.py --dry-run       show what would change, write nothing
  mirror.py --check         print resolved paths and counts, write nothing
  mirror.py --uncategorized list memories that fell into "General" (for writing new rules)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

MARKER = "mnemosyne-obsidian-mirror"
DEFAULT_FOLDER = "Hermes Memory"
DEFAULT_INDEX = "Hermes Memory Index"
GENERAL = "General"

# Mnemosyne `source` -> type label. Unknown sources become a title-cased label.
TYPE_MAP = {
    "preference": "Preferences",
    "user": "Preferences",
    "builtin_memory_user": "Preferences",
    "fact": "Facts",
    "builtin_memory_memory": "Facts",
    "tool": "Tools and setup",
    "task": "Tasks and progress",
    "task:progress": "Tasks and progress",
    "insight": "Insights",
    "skill_update": "Skill updates",
    "triple": "Knowledge graph",
    "conversation_summary": "Conversation summaries",
}
TYPE_ORDER = ["Preferences", "Facts", "Insights", "Tools and setup",
              "Tasks and progress", "Skill updates", "Knowledge graph", "Conversation summaries"]

# Raw chat turns and model scratch are not memories worth mirroring.
SKIP_SOURCES = {"conversation"}
SKIP_PREFIXES = ("[conversation]", "<think>")


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes").expanduser()


def env_from_dotenv(name: str) -> str | None:
    """Process env first, then $HERMES_HOME/.env (simple KEY=VALUE lines)."""
    if os.environ.get(name):
        return os.environ[name]
    env_file = hermes_home() / ".env"
    if env_file.is_file():
        for line in env_file.read_text(errors="replace").splitlines():
            m = re.match(rf"\s*(?:export\s+)?{re.escape(name)}\s*=\s*(.*)$", line)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return None


def type_label(source: str) -> str:
    source = (source or "").strip()
    if source in TYPE_MAP:
        return TYPE_MAP[source]
    return source.replace("_", " ").replace(":", " ").strip().capitalize() or "Other"


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|#^\[\]]', "-", name).strip(" .")
    return cleaned or "Untitled"


def normalise(text: str) -> str:
    text = re.sub(r"^\[[^\]]+\]\s*", "", text.strip())
    return re.sub(r"\s+", " ", text).lower()


# ---------------------------------------------------------------- loading

def table_columns(cur: sqlite3.Cursor, table: str) -> set[str]:
    return {r[1] for r in cur.execute(f"pragma table_info({table})")}


def load_memories(db_path: Path, include_summaries: bool = False) -> list[dict]:
    """Return current (not superseded, not expired) curated memories, deduplicated."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = con.cursor()
    tables = {r[0] for r in cur.execute("select name from sqlite_master where type='table'")}
    now = datetime.now().isoformat(sep=" ")
    out: list[dict] = []
    seen: set[str] = set()

    def add(mid, content, source, when, importance):
        content = (content or "").strip()
        if not content or source in SKIP_SOURCES or content.startswith(SKIP_PREFIXES):
            return
        key = normalise(content)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "id": str(mid),
            "content": content,
            "source": source or "",
            "date": (when or "")[:10],
            "importance": importance,
        })

    working_ids: set[str] = set()
    if "working_memory" in tables:
        rows = cur.execute(
            "select id, content, source, coalesce(timestamp, created_at), importance "
            "from working_memory where superseded_by is null "
            "and (valid_until is null or valid_until > ?) order by coalesce(timestamp, created_at)",
            (now,),
        ).fetchall()
        for mid, content, source, when, imp in rows:
            working_ids.add(mid)
            add(mid, content, source, when, imp)

    if "episodic_memory" in tables:
        cols = table_columns(cur, "episodic_memory")
        summary_col = "summary_of" if "summary_of" in cols else "null"
        rows = cur.execute(
            f"select id, content, source, coalesce(timestamp, created_at), importance, {summary_col} "
            "from episodic_memory where superseded_by is null "
            "and (valid_until is null or valid_until > ?) order by coalesce(timestamp, created_at)",
            (now,),
        ).fetchall()
        for mid, content, _source, when, imp, summary_of in rows:
            if summary_of and summary_of in working_ids:
                continue  # summary of a memory we already mirror
            m = re.match(r"^\[([^\]]+)\]\s*", content or "")
            if m:  # consolidated copy of a curated memory: "[fact] ..."
                add(mid, content[m.end():], m.group(1), when, imp)
            elif include_summaries:  # free-text summary of chat turns, often noisy
                add(mid, content, "conversation_summary", when, imp)

    if "canonical_facts" in tables:
        rows = cur.execute(
            "select id, name, body, category, coalesce(valid_from, created_at), confidence "
            "from canonical_facts where valid_until is null or valid_until > ?",
            (now,),
        ).fetchall()
        for mid, name, body, category, when, conf in rows:
            add(f"canonical-{mid}", f"{name}: {body}", category or "fact", when, conf)

    if "triples" in tables:
        rows = cur.execute(
            "select id, subject, predicate, object, coalesce(valid_from, created_at), confidence "
            "from triples where valid_until is null or valid_until > ?",
            (now,),
        ).fetchall()
        for mid, s, p, o, when, conf in rows:
            add(f"triple-{mid}", f"{s} -- {p} --> {o}", "triple", when, conf)

    con.close()
    return out


def load_rules(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    data = json.loads(path.read_text())
    rules = []
    for r in data.get("topics", []):
        name = str(r.get("name", "")).strip()
        if not name:
            continue
        keywords = [k.lower() for k in r.get("keywords", []) if k]
        sources = {s for s in r.get("sources", []) if s}
        rules.append({"name": name, "keywords": keywords, "sources": sources})
    return rules


def topic_for(memory: dict, rules: list[dict]) -> str:
    text = memory["content"].lower()
    for r in rules:
        if memory["source"] in r["sources"]:
            return r["name"]
        if any(k in text for k in r["keywords"]):
            return r["name"]
    return GENERAL


# ---------------------------------------------------------------- rendering

def frontmatter(kind: str, tags: list[str]) -> str:
    tag_lines = "".join(f"  - {t}\n" for t in tags)
    return f"---\ngenerated_by: {MARKER}\nkind: {kind}\ntags:\n{tag_lines}---\n"


def render_item(m: dict, link: str | None) -> str:
    lines = m["content"].splitlines() or [""]
    body = lines[0] + "".join(f"\n  {ln}" for ln in lines[1:])
    meta = [m["date"] or "undated"]
    if isinstance(m["importance"], (int, float)):
        meta.append(f"importance {m['importance']:.2f}")
    if link:
        meta.append(link)
    meta.append(f"id {m['id']}")
    return f"- {body}\n  *{' · '.join(meta)}*\n"


def ordered_types(types) -> list[str]:
    return sorted(types, key=lambda t: (TYPE_ORDER.index(t) if t in TYPE_ORDER else len(TYPE_ORDER), t))


def build_notes(memories: list[dict], rules: list[dict]) -> dict[str, str]:
    by_topic: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    by_type: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for m in memories:
        topic, typ = topic_for(m, rules), type_label(m["source"])
        by_topic[topic][typ].append(m)
        by_type[typ][topic].append(m)

    rule_order = [r["name"] for r in rules]
    topics = sorted(by_topic, key=lambda t: (t == GENERAL, rule_order.index(t) if t in rule_order else 999, t))
    types = ordered_types(by_type)
    notes: dict[str, str] = {}

    for topic in topics:
        fname = safe_filename(topic)
        parts = [frontmatter("topic", ["hermes-memory", f"hermes-memory/topic/{slug(topic)}"]),
                 f"# {topic}\n\nBack to [[{DEFAULT_INDEX}|Hermes Memory index]]\n"]
        for typ in ordered_types(by_topic[topic]):
            items = sorted(by_topic[topic][typ], key=lambda m: m["date"], reverse=True)
            parts.append(f"\n## {typ} ({len(items)})\n\n")
            parts.extend(render_item(m, None) for m in items)
        notes[f"Topics/{fname}.md"] = "".join(parts)

    for typ in types:
        fname = safe_filename(typ)
        parts = [frontmatter("type", ["hermes-memory", f"hermes-memory/type/{slug(typ)}"]),
                 f"# {typ}\n\nBack to [[{DEFAULT_INDEX}|Hermes Memory index]]\n"]
        for topic in [t for t in topics if t in by_type[typ]]:
            items = sorted(by_type[typ][topic], key=lambda m: m["date"], reverse=True)
            parts.append(f"\n## [[{safe_filename(topic)}|{topic}]] ({len(items)})\n\n")
            parts.extend(render_item(m, None) for m in items)
        notes[f"Types/{fname}.md"] = "".join(parts)

    index = [frontmatter("index", ["hermes-memory"]),
             "# Hermes Memory\n\n",
             "Read-only mirror of Hermes' Mnemosyne memory, refreshed by a scheduled job. "
             "Edits here are overwritten on the next run and never flow back to Mnemosyne; "
             "ask Hermes to remember or forget things instead.\n\n",
             f"{len(memories)} memories in {len(topics)} topics and {len(types)} types.\n\n",
             "## Topics\n\n"]
    index += [f"- [[{safe_filename(t)}|{t}]] ({sum(len(v) for v in by_topic[t].values())})\n" for t in topics]
    index.append("\n## Types\n\n")
    index += [f"- [[{safe_filename(t)}|{t}]] ({sum(len(v) for v in by_type[t].values())})\n" for t in types]
    notes[f"{DEFAULT_INDEX}.md"] = "".join(index)

    # A topic and a type with the same name would collide on [[links]]; disambiguate the type.
    topic_names = {safe_filename(t) for t in topics}
    for typ in types:
        if safe_filename(typ) in topic_names:
            raise SystemExit(f"topic name '{typ}' collides with a type name; rename the topic rule")
    return notes


# ---------------------------------------------------------------- writing

def is_generated(path: Path) -> bool:
    try:
        head = path.read_text(errors="replace")[:300]
    except OSError:
        return False
    return head.startswith("---") and f"generated_by: {MARKER}" in head


def sync(out_dir: Path, notes: dict[str, str], dry_run: bool) -> tuple[list[str], list[str]]:
    changed, removed = [], []
    for rel, text in notes.items():
        path = out_dir / rel
        if path.exists():
            if not is_generated(path):
                raise SystemExit(f"refusing to overwrite non-generated note: {path}")
            if path.read_text(errors="replace") == text:
                continue
        changed.append(rel)
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".md.tmp")
            tmp.write_text(text)
            os.replace(tmp, path)
    if out_dir.is_dir():
        for path in out_dir.rglob("*.md"):
            rel = path.relative_to(out_dir).as_posix()
            if rel not in notes and is_generated(path):
                removed.append(rel)
                if not dry_run:
                    path.unlink()
    return changed, removed


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vault", help="Obsidian vault path (default: OBSIDIAN_VAULT_PATH)")
    ap.add_argument("--folder", default=DEFAULT_FOLDER, help=f"folder inside the vault (default: {DEFAULT_FOLDER})")
    ap.add_argument("--db", help="Mnemosyne DB (default: MNEMOSYNE_DB or $HERMES_HOME/mnemosyne/data/mnemosyne.db)")
    ap.add_argument("--rules", help="topic rules JSON (default: $HERMES_HOME/mnemosyne-obsidian/categories.json)")
    ap.add_argument("--include-summaries", action="store_true",
                    help="also mirror Mnemosyne's free-text conversation summaries (noisy; off by default)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--uncategorized", action="store_true")
    args = ap.parse_args(argv)

    vault = args.vault or env_from_dotenv("OBSIDIAN_VAULT_PATH")
    if not vault:
        print("error: no vault: pass --vault or set OBSIDIAN_VAULT_PATH", file=sys.stderr)
        return 2
    vault_path = Path(vault).expanduser()
    if not vault_path.is_dir():
        print(f"error: vault not found: {vault_path}", file=sys.stderr)
        return 2
    db = Path(args.db or env_from_dotenv("MNEMOSYNE_DB") or hermes_home() / "mnemosyne/data/mnemosyne.db").expanduser()
    if not db.is_file():
        print(f"error: Mnemosyne DB not found: {db}", file=sys.stderr)
        return 2
    rules_path = Path(args.rules).expanduser() if args.rules else hermes_home() / "mnemosyne-obsidian/categories.json"
    out_dir = vault_path / args.folder

    memories = load_memories(db, args.include_summaries)
    rules = load_rules(rules_path)

    if args.check:
        print(f"db:      {db}\nvault:   {vault_path}\nfolder:  {out_dir}")
        print(f"rules:   {rules_path} ({'found, ' + str(len(rules)) + ' topics' if rules_path.is_file() else 'missing: everything goes to General'})")
        general = sum(topic_for(m, rules) == GENERAL for m in memories)
        print(f"memories: {len(memories)} ({general} uncategorized)")
        return 0

    if args.uncategorized:
        for m in memories:
            if topic_for(m, rules) == GENERAL:
                print(f"[{m['source']}] {m['date']} {m['id']}: {m['content'][:200]}")
        return 0

    notes = build_notes(memories, rules)
    changed, removed = sync(out_dir, notes, args.dry_run)
    if changed or removed:
        verb = "Would update" if args.dry_run else "Updated"
        print(f"{verb} Hermes Memory mirror: {len(memories)} memories, "
              f"{len(changed)} notes written, {len(removed)} removed ({out_dir})")
        if args.dry_run:
            for rel in changed:
                print(f"  write  {rel}")
            for rel in removed:
                print(f"  remove {rel}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
