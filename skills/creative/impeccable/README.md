# impeccable

Vendored copy of [Impeccable](https://impeccable.style/) by Paul Bakaus ([`pbakaus/impeccable`](https://github.com/pbakaus/impeccable), Apache 2.0): design vocabulary and commands for agents building or refining frontend UI (`critique`, `audit`, `polish`, `typeset`, `layout`, `live`, `document`, ...), plus a code-only design detector.

Provenance: the Hermes build produced by `npx impeccable install -y --providers=hermes --global`, skill version 4.9.0, engine 0.1.23 (`scripts/VERSION`). Files are byte-identical to that install so future syncs diff cleanly. SKILL.md and the references keep upstream's `.hermes/skills/impeccable/...` fallback path, so install it at that top-level location.

The engine binary (`scripts/bin/`, ~17 MB per platform) is NOT committed. On first run the `scripts/impeccable` launcher downloads it from the upstream GitHub release and checks it against `scripts/engine-checksums.txt`; no Node runtime is needed.

## Install

    ln -s <this-repo>/skills/creative/impeccable ~/.hermes/skills/impeccable
    ~/.hermes/skills/impeccable/scripts/impeccable context   # fetches the engine once

Or install upstream directly: `npx impeccable install -y --providers=hermes --global`.

## Use

Hermes has no per-skill slash command; ask for design work ("critique this page", "polish the pricing page", "redesign the docs site with impeccable") and the agent loads the skill. The command table in SKILL.md lists every sub-command and its reference file.

## Updating

Re-run the upstream installer into a scratch HOME, `diff -r` it against this folder, copy changes in, bump the version noted above.
