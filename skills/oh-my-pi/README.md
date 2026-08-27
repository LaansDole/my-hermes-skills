# oh-my-pi

Troubleshoot and operate the **Oh-My-Pi (omp)** coding agent
([can1357/oh-my-pi](https://github.com/can1357/oh-my-pi), a fork of
[earendil-works/pi](https://pi.dev)). Covers the `hub` coordination tool, task
agents & model routing, the two-tier review pattern, silent provider/model
fallback, extension/plugin mechanics, and user-authored task agents (the `tldr`
and `pr` roles), with source-verified internals for the fork.

## What's in here

- `SKILL.md` — the operational guide: identity/disambiguation, `hub` semantics,
  the "agent looks stuck" diagnosis recipe, task-agent model routing, the two-tier
  reviewer, OAuth fallback diagnosis, and installing pi-format extensions.
- `references/source-verified-mechanics.md` — exact file paths, line-level
  evidence, and code locations from the oh-my-pi repo (so future sessions skip the
  re-clone): `hub wait` race, poll ladder, bundled agent defs + model resolution,
  `task` tool guidance, and the extension API / session-manager surface.
- `scripts/omp-rpc-extension-smoke.ts` — ambient RPC smoke probe: verifies an
  extension under `~/.omp/plugins` loads on the real omp binary (manifest
  discovery) and registers its commands.

## Provenance

Author-maintained by Hermes Agent (Nous Research) over multiple sessions (Aug
2026). This is the source-of-truth copy; it is symlinked at
`~/.hermes/skills/autonomous-ai-agents/oh-my-pi`. Updates go through LaansDole's
Hermes workflow — edit here, commit, push, and the live symlink picks it up.

## Category

Top-level `skills/oh-my-pi/` maps to the **Coding Agents** section of the docs
site (see `scripts/generate_docs.py` `CATEGORY_MAP`).