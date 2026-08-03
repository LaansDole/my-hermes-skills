---
name: superpowers-using-git-worktrees
description: "Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification"
version: 1.0.0
author: "Labhund (derived from obra/superpowers)"
license: MIT
metadata:
  hermes:
    tags: [superpowers, git, worktrees, isolation]
    related_skills: [superpowers-subagent-driven-development, superpowers-finishing-a-development-branch]
---

# Using Git Worktrees

## Overview

Git worktrees create isolated workspaces sharing the same repository, allowing work on multiple branches simultaneously without switching.

**Core principle:** Systematic directory selection + safety verification = reliable isolation.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Directory Selection Process

Follow this priority order:

### 1. Check Existing Directories

```text
terminal(command="ls -d .worktrees 2>/dev/null")   # Preferred (hidden)
terminal(command="ls -d worktrees 2>/dev/null")    # Alternative
```

**If found:** Use that directory. If both exist, `.worktrees` wins.

### 2. Check Project Context Files

```text
terminal(command="grep -i 'worktree.*director' AGENTS.md CLAUDE.md .hermes.md 2>/dev/null")
```

(Hermes reads `AGENTS.md`, `CLAUDE.md`, and `.hermes.md` as project context — check whichever exist.)

**If preference specified:** Use it without asking.

### 3. Ask User

If no directory exists and no project-context-file preference:

```text
No worktree directory found. Where should I create worktrees?

1. .worktrees/ (project-local, hidden)
2. ~/.config/superpowers/worktrees/<project-name>/ (global location)

Which would you prefer?
```

## Safety Verification

### For Project-Local Directories (.worktrees or worktrees)

**MUST verify directory is ignored before creating worktree:**

```text
terminal(command="git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null")
```

**If NOT ignored:**

Per Jesse's rule "Fix broken things immediately":
1. Add appropriate line to .gitignore
2. Commit the change
3. Proceed with worktree creation

**Why critical:** Prevents accidentally committing worktree contents to repository.

### For Global Directory (~/.config/superpowers/worktrees)

No .gitignore verification needed - outside project entirely.

## Creation Steps

### 1. Detect Project Name

```text
terminal(command="basename \"$(git rev-parse --show-toplevel)\"")
```

### 2. Create Worktree

```text
# Determine full path
#   .worktrees/<branch> or worktrees/<branch> for project-local
#   ~/.config/superpowers/worktrees/<project>/<branch> for global

terminal(command="git worktree add \"$LOCATION/$BRANCH_NAME\" -b \"$BRANCH_NAME\"")
# then set cwd to the new worktree path for subsequent commands
```

### 3. Run Project Setup

Auto-detect and run appropriate setup (from the new worktree dir):

```text
terminal(command="[ -f package.json ] && npm install")        # Node.js
terminal(command="[ -f Cargo.toml ] && cargo build")          # Rust
terminal(command="[ -f requirements.txt ] && pip install -r requirements.txt")  # Python
terminal(command="[ -f pyproject.toml ] && poetry install")   # Python (poetry)
terminal(command="[ -f go.mod ] && go mod download")          # Go
```

### 4. Verify Clean Baseline

Run tests to ensure worktree starts clean (use the project-appropriate command):

```text
terminal(command="npm test")          # Node.js
terminal(command="cargo test")        # Rust
terminal(command="pytest")            # Python
terminal(command="go test ./...")     # Go
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

### 5. Report Location

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Quick Reference

| Situation | Action |
|-----------|--------|
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check AGENTS.md/CLAUDE.md/.hermes.md → Ask user |
| Directory not ignored | Add to .gitignore + commit |
| Tests fail during baseline | Report failures + ask |
| No package.json/Cargo.toml | Skip dependency install |

## Common Mistakes

### Skipping ignore verification

- **Problem:** Worktree contents get tracked, pollute git status
- **Fix:** Always use `git check-ignore` before creating project-local worktree

### Assuming directory location

- **Problem:** Creates inconsistency, violates project conventions
- **Fix:** Follow priority: existing > AGENTS.md/CLAUDE.md > ask

### Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues
- **Fix:** Report failures, get explicit permission to proceed

### Hardcoding setup commands

- **Problem:** Breaks on projects using different tools
- **Fix:** Auto-detect from project files (package.json, etc.)

## Example Workflow

```
You: I'm using the using-git-worktrees skill to set up an isolated workspace.

[Check .worktrees/ - exists]
[Verify ignored - git check-ignore confirms .worktrees/ is ignored]
[Create worktree: git worktree add .worktrees/auth -b feature/auth]
[Run npm install]
[Run npm test - 47 passing]

Worktree ready at /Users/jesse/myproject/.worktrees/auth
Tests passing (47 tests, 0 failures)
Ready to implement auth feature
```

## Red Flags

**Never:**
- Create worktree without verifying it's ignored (project-local)
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous
- Skip AGENTS.md/CLAUDE.md/.hermes.md check

**Always:**
- Follow directory priority: existing > AGENTS.md/CLAUDE.md > ask
- Verify directory is ignored for project-local
- Auto-detect and run project setup
- Verify clean test baseline

## Integration

**Called by:**
- **brainstorming** (Phase 4) - REQUIRED when design is approved and implementation follows
- **subagent-driven-development** - REQUIRED before executing any tasks
- **executing-plans** - REQUIRED before executing any tasks
- Any skill needing isolated workspace

**Pairs with:**
- **finishing-a-development-branch** - REQUIRED for cleanup after work complete
