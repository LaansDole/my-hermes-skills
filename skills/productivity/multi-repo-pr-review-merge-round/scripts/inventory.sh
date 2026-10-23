#!/bin/bash
# Inventory open PRs (on ORIGIN, not the fork's upstream) and worktrees.
# usage: inventory.sh <repo-or-parent-dir> [...]
# A parent dir that is not a git repo is expanded to its child repos.
inv() {
  local r=$1
  local url owner_repo
  url=$(git -C "$r" remote get-url origin 2>/dev/null) || return
  owner_repo=$(echo "$url" | sed -E 's|.*github\.com[:/]||; s|\.git$||')
  echo "=== $r  ($owner_repo)"
  git -C "$r" fetch -q origin 2>/dev/null
  gh pr list --repo "$owner_repo" --state open \
    --json number,title,headRefName,baseRefName,isDraft,mergeable,mergeStateStatus,additions,deletions \
    --jq '.[]|"PR #\(.number) \(.headRefName) -> \(.baseRefName) \(.mergeable)/\(.mergeStateStatus) +\(.additions)/-\(.deletions)\(if .isDraft then " DRAFT" else "" end)  \(.title)"'
  git -C "$r" worktree list --porcelain | awk '/^worktree /{print $2}' | while read -r w; do
    local st ahead dirty
    st=$(git -C "$w" status -sb | head -1)
    dirty=$(git -C "$w" status --short | grep -vcE '^\?\? (\.pi|\.bun-cache)/')
    echo "  WT $w :: $st :: dirty=$dirty"
  done
}
for arg in "$@"; do
  if git -C "$arg" rev-parse --git-dir >/dev/null 2>&1; then inv "$arg"
  else for c in "$arg"/*/; do git -C "$c" rev-parse --show-toplevel 2>/dev/null | grep -qx "${c%/}" && inv "${c%/}"; done
  fi
done
