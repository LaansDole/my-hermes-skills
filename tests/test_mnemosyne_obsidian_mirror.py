import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/productivity/mnemosyne-obsidian-mirror/scripts/mirror.py"
spec = importlib.util.spec_from_file_location("mirror", SCRIPT)
assert spec and spec.loader
mirror = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mirror)


def make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        create table working_memory (id text, content text, source text, timestamp text, created_at text,
            importance real, superseded_by text, valid_until text);
        create table episodic_memory (id text, content text, source text, timestamp text, created_at text,
            importance real, summary_of text, superseded_by text, valid_until text);
        create table canonical_facts (id integer, name text, body text, category text, valid_from text,
            created_at text, confidence real, valid_until text);
        create table triples (id integer, subject text, predicate text, object text, valid_from text,
            created_at text, confidence real, valid_until text);
        """
    )
    w = [
        ("w1", "Prefers short answers", "preference", "2026-01-02T10:00:00", None, 0.9, None, None),
        ("w2", "Project Alpha uses Postgres 16", "fact", "2026-01-03T10:00:00", None, 0.7, None, None),
        ("w3", "[USER] hello there", "conversation", "2026-01-04T10:00:00", None, 0.5, None, None),
        ("w4", "Old alpha fact", "fact", "2026-01-01T10:00:00", None, 0.7, "w2", None),
        ("w5", "Expired fact", "fact", "2026-01-01T10:00:00", None, 0.7, None, "2000-01-01"),
        ("w6", "prefers  SHORT answers", "builtin_memory_user", "2026-01-05T10:00:00", None, 0.9, None, None),
        ("w7", "Paper X excluded", "review_verdict", "2026-01-06T10:00:00", None, 0.8, None, None),
    ]
    con.executemany("insert into working_memory values (?,?,?,?,?,?,?,?)", w)
    e = [
        ("e1", "[fact] Project Alpha uses Postgres 16", "sleep_consolidation", "2026-01-07", None, 0.6, "w2", None, None),
        ("e2", "[insight] Beta deploys break on Fridays", "sleep_consolidation", "2026-01-08", None, 0.6, "gone", None, None),
        ("e3", "[conversation] [USER] hi", "sleep_consolidation", "2026-01-08", None, 0.6, None, None, None),
        ("e4", "<think>\nsummarise", "sleep_consolidation", "2026-01-08", None, 0.6, None, None, None),
        ("e5", "The user discussed beta plans", "sleep_consolidation", "2026-01-09", None, 0.6, None, None, None),
    ]
    con.executemany("insert into episodic_memory values (?,?,?,?,?,?,?,?,?)", e)
    con.execute("insert into canonical_facts values (1,'alpha-migration','done','task:progress','2026-01-10',null,1.0,null)")
    con.execute("insert into triples values (1,'alpha','depends-on','postgres','2026-01-11',null,1.0,null)")
    con.commit()
    con.close()


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.db = root / "m.db"
        make_db(self.db)
        self.vault = root / "vault"
        self.vault.mkdir()
        self.rules = root / "rules.json"
        self.rules.write_text(json.dumps({"topics": [
            {"name": "Reviews", "sources": ["review_verdict"]},
            {"name": "Alpha", "keywords": ["alpha"]},
            {"name": "Beta", "keywords": ["beta"]},
        ]}))
        self.out = self.vault / "Hermes Memory"

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *extra):
        return mirror.main(["--vault", str(self.vault), "--db", str(self.db), "--rules", str(self.rules), *extra])

    def test_load_filters_and_dedupes(self):
        mems = mirror.load_memories(self.db)
        contents = [m["content"] for m in mems]
        self.assertIn("Prefers short answers", contents)
        self.assertNotIn("prefers  SHORT answers", contents)  # normalised duplicate
        self.assertNotIn("Old alpha fact", contents)  # superseded
        self.assertNotIn("Expired fact", contents)
        self.assertFalse(any("hello there" in c or "<think>" in c or "[USER]" in c for c in contents))
        self.assertIn("Beta deploys break on Fridays", contents)  # episodic not covered by working
        self.assertEqual(sum(c == "Project Alpha uses Postgres 16" for c in contents), 1)
        self.assertNotIn("The user discussed beta plans", contents)  # summaries are opt-in
        self.assertIn("alpha-migration: done", contents)
        self.assertIn("alpha -- depends-on --> postgres", contents)

    def test_summaries_opt_in(self):
        contents = [m["content"] for m in mirror.load_memories(self.db, include_summaries=True)]
        self.assertIn("The user discussed beta plans", contents)

    def test_categorisation(self):
        rules = mirror.load_rules(self.rules)
        by_content = {m["content"]: m for m in mirror.load_memories(self.db)}
        self.assertEqual(mirror.topic_for(by_content["Paper X excluded"], rules), "Reviews")
        self.assertEqual(mirror.topic_for(by_content["Project Alpha uses Postgres 16"], rules), "Alpha")
        self.assertEqual(mirror.topic_for(by_content["Prefers short answers"], rules), "General")
        self.assertEqual(mirror.type_label("builtin_memory_user"), "Preferences")
        self.assertEqual(mirror.type_label("task:progress"), "Tasks and progress")
        self.assertEqual(mirror.type_label("review_verdict"), "Review verdict")

    def test_write_is_idempotent_and_prunes_only_generated(self):
        self.assertEqual(self.run_main(), 0)
        index = (self.out / "Hermes Memory Index.md").read_text()
        self.assertIn("[[Alpha|Alpha]]", index)
        alpha = (self.out / "Topics/Alpha.md").read_text()
        self.assertIn("generated_by: mnemosyne-obsidian-mirror", alpha)
        self.assertIn("## Facts (1)", alpha)
        self.assertTrue((self.out / "Types/Preferences.md").is_file())

        user_note = self.out / "My own note.md"
        user_note.write_text("# mine\n")
        stale = self.out / "Topics/Gone.md"
        stale.write_text("---\ngenerated_by: mnemosyne-obsidian-mirror\n---\nold\n")
        before = {p: p.stat().st_mtime_ns for p in self.out.rglob("*.md") if p not in (user_note, stale)}

        _, removed = mirror.sync(self.out, mirror.build_notes(mirror.load_memories(self.db),
                                                             mirror.load_rules(self.rules)), dry_run=False)
        self.assertEqual(removed, ["Topics/Gone.md"])
        self.assertTrue(user_note.is_file())
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in before})  # unchanged notes untouched

    def test_refuses_to_overwrite_user_note(self):
        (self.out / "Topics").mkdir(parents=True)
        (self.out / "Topics/Alpha.md").write_text("# my hand-written alpha note\n")
        with self.assertRaises(SystemExit):
            self.run_main()

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.run_main("--dry-run"), 0)
        self.assertFalse(self.out.exists())

    def test_database_untouched(self):
        before = self.db.read_bytes()
        self.run_main()
        self.assertEqual(before, self.db.read_bytes())


if __name__ == "__main__":
    unittest.main()
