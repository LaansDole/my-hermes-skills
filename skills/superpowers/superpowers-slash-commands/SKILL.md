---
name: superpowers-slash-commands
description: "Index and invocation guide for the Superpowers skills. Use when the user asks for a Superpowers skill by name or wants to know which skills exist."
version: 1.0.0
author: "Labhund (derived from obra/superpowers)"
license: MIT
metadata:
  hermes:
    tags: [superpowers, skills, navigation]
    related_skills: [superpowers-using-superpowers]
---

# Superpowers Skills Index

Reference index of the Superpowers skill library. Hermes loads skills by description matching and via `/skill <name>` — there is no custom `/superpowers-` command dispatcher in Hermes.

## Available Skills

### Planning
- `superpowers-brainstorming` - Turn ideas into fully formed designs (Socratic questioning, alternatives, design approval)
- `superpowers-writing-plans` - Create detailed implementation plans with bite-sized tasks and exact file paths

### Execution
- `superpowers-subagent-driven-development` - Dispatch a fresh subagent per task with two-stage review (spec compliance → code quality)
- `superpowers-executing-plans` - Batch execution of a plan in the current session with verification checkpoints
- `superpowers-dispatching-parallel-agents` - Concurrent subagent dispatch for independent tasks
- `superpowers-test-driven-development` - RED-GREEN-REFACTOR TDD cycle
- `superpowers-systematic-debugging` - 4-phase root cause investigation (trace → analyze → test → verify)

### Review
- `superpowers-requesting-code-review` - Dispatch a code-reviewer subagent before merge
- `superpowers-receiving-code-review` - Respond to review feedback with technical rigor

### Completion
- `superpowers-verification-before-completion` - Verify with commands and real output before claiming success
- `superpowers-finishing-a-development-branch` - Verify tests, present merge/PR/cleanup options

### Infrastructure
- `superpowers-using-git-worktrees` - Isolated git worktrees with smart directory selection
- `superpowers-writing-skills` - Create new skills following best practices
- `superpowers-using-superpowers` - How the skill system works in Hermes

## How to Invoke

Hermes picks these up automatically from conversation triggers (e.g. "something's wrong" → superpowers-systematic-debugging). To invoke explicitly:

```text
/skill superpowers-brainstorming
```

or in a fresh session: `hermes -s superpowers-brainstorming`.

## Namespace Philosophy

All Superpowers skills are prefixed with `superpowers-` to:

- Prevent naming conflicts with native Hermes skills
- Make it clear which skill system is being used
- Allow comparison between similar workflows (e.g., `test-driven-development` vs `superpowers-test-driven-development`)
- Enable selective usage of either system
