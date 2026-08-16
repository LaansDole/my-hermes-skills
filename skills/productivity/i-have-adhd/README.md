# i-have-adhd

Output-shaping skill for a reader with ADHD: lead with the next action, number multi-step work, restate state across turns, suppress tangents, give specific time estimates, make wins visible.

Vendored from [`ayghri/i-have-adhd`](https://github.com/ayghri/i-have-adhd) (MIT) at upstream `main` (2ed0640). Keep the skill folder byte-identical to upstream so future syncs stay clean diffs.

## How it works

- The skill's `SKILL.md` carries the full ruleset (10 rules + break-the-rules exceptions + pre-send check).
- Hermes has **no** `/i-have-adhd` slash command (the upstream INSTALL.md's Hermes section is inaccurate there — that's a Claude Code / Pi convention). In Hermes you activate it by asking the agent directly, e.g. "use i-have-adhd mode" or "enable ADHD output style", and turn it off with "stop adhd mode".
- The frontmatter has `disable-model-invocation: true` (upstream's opt-in posture: the agent should not apply it unprompted).

## Install

```bash
ln -s <repo>/skills/productivity/i-have-adhd ~/.hermes/skills/productivity/i-have-adhd
```

## Always-on (optional)

Add the "Output style" block from the upstream INSTALL.md to this repo's `AGENTS.md` or the persona `SOUL.md` — then every response is shaped without being asked. See the skill's `agents/gemini.toml` for the compact always-on variant.
