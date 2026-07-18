# auto-learn-for-me

Autonomously advance HCL iLearning Success courses with Hermes Agent.

## What this is

A Hermes Agent skill pack that watches course videos in your own Chrome session (via CDP) and autonomously clicks "continue"/"next" to advance through modules, answers in-video quizzes, and navigates between lessons. Fully unattended.

## Quick start

1. One-time setup: follow `~/.hermes/skills/ilearning-autoadvance/SETUP.md`.
2. Per session:
   ```bash
   # Start Chrome with remote debugging, log into HCL iLearning, open a lesson
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9222 \
     --user-data-dir="$HOME/Library/Application Support/Google/Chrome" &

   # Start Hermes
   hermes -t browser chat
   # then in Hermes: /browser connect
   # then: Run the ilearning-autoadvance skill on my current tab, max_modules=10
   ```

## First-run safety

Do a dry run first (`dry_run=true`, `max_modules=1`) to validate state classification against the real HCL iLearning DOM. Then a single-module live run with approvals on (`approvals.mode: manual`). Then the full unattended run.

## Repository layout

```
.
├── README.md                                    # this file
├── .hermes-config/
│   └── config-patch.yaml                        # merge into ~/.hermes/config.yaml after install
└── docs/superpowers/
    ├── specs/
    │   └── 2026-07-18-hermes-iLearning-autoadvance-design.md   # design spec
    └── plans/
        └── 2026-07-18-hermes-iLearning-autoadvance.md         # implementation plan
```

The runtime deliverables — `SKILL.md` and `SETUP.md` — live in `~/.hermes/skills/ilearning-autoadvance/`, outside this repo (Hermes auto-discovers skills there).

## Design and implementation

- Design spec: `docs/superpowers/specs/2026-07-18-hermes-iLearning-autoadvance-design.md`
- Implementation plan: `docs/superpowers/plans/2026-07-18-hermes-iLearning-autoadvance.md`
