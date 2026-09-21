---
name: oh-my-ghostty
description: Use when setting up or refreshing the oh-my-ghostty terminal stack on macOS - Ghostty config, fastfetch on new-terminal startup, and bat/eza/zoxide aliases for zsh.
version: 1.0.0
metadata:
  hermes:
    tags: [ghostty, terminal, zsh, fastfetch, bat, eza, zoxide, macos]
    requires_toolsets: [terminal]
---

# oh-my-ghostty

Set up the [sudo-conner/oh-my-ghostty](https://github.com/sudo-conner/oh-my-ghostty) terminal stack on macOS: Ghostty theme config, fastfetch on every new terminal, and the bat/eza/zoxide aliases in zsh. Assumes Oh My Zsh + Powerlevel10k are already installed and configured — this skill never touches them (user preference: p10k theme stays as-is).

## When to use

- "Set up oh-my-ghostty", "make my terminal like oh-my-ghostty", "add fastfetch on startup", "replace cat/ls with bat/eza".
- Refreshing any piece of the stack after a Ghostty upgrade or new machine.

## What the repo actually is

The GitHub repo is a **blog-style guide**, not an installable framework — no script to run. It documents: Ghostty (brew cask), Oh My Zsh, p10k, fastfetch, zsh-syntax-highlighting + zsh-autosuggestions, and two aliases (`cat`→bat, `ls`→eza) plus a plain zoxide init (no `cd` alias). Apply it manually; everything is idempotent.

## Setup (macOS, Homebrew)

1. Install what's missing — check first, only install gaps:
   ```bash
   brew list --formula | grep -E "^(bat|eza|zoxide|fastfetch)$"
   brew install bat eza zoxide   # fastfetch too if absent
   ```
   Ghostty itself: `brew install --cask ghostty`. Its CLI is NOT on PATH by default — use the full binary:
   ```bash
   /Applications/Ghostty.app/Contents/MacOS/ghostty
   ```

2. Ghostty config — create `~/.config/ghostty/config` if absent:
   ```
   # oh-my-ghostty — https://github.com/sudo-conner/oh-my-ghostty
   theme = Catppuccin Frappe
   ```
   Validate before declaring success:
   ```bash
   /Applications/Ghostty.app/Contents/MacOS/ghostty +validate-config
   ```
   Discover valid theme names with `+list-themes | grep -i catppuccin`.

3. zsh block — append to `~/.zshrc` as a marked block (re-runs replace the block between the markers; never duplicate):
   ```zsh
   # >>> BEGIN OH-MY-GHOSTTY (https://github.com/sudo-conner/oh-my-ghostty) >>>

   # fastfetch on new terminal startup (skip in nested shells to keep serial/agent terminals clean)
   if [[ $SHLVL -eq 1 && -o interactive && -x "$(command -v fastfetch)" ]]; then
     fastfetch
   fi

   # zoxide (smarter cd) — must init after compinit
   eval "$(zoxide init zsh)"

   # Aliases
   alias cat="bat --paging=never"
   alias ls="eza -lao --git-repos --header --icons"

   # <<< END OH-MY-GHOSTTY <<<
   ```

4. zsh-syntax-highlighting / zsh-autosuggestions — the repo adds these too, but they are oh-my-zsh *plugins* in `~/.oh-my-zsh/custom/plugins/`, not brew-managed here. If the user's `.zshrc` plugins array already lists them, skip (do not install brew duplicates).

## Gotchas

- **Theme name**: the repo README says `theme = catppuccin-frappe`; Ghostty 1.3.1 rejects it — the built-in name is `Catppuccin Frappe` (spaces, mixed case). `+validate-config` catches this.
- **fastfetch guard**: without `SHLVL -eq 1`, fastfetch prints in every nested shell — including agent/serial terminal sessions, polluting tool output. The `-x "$(command -v fastfetch)"` check keeps shells working if brew package is removed.
- **zoxide init order**: must come after oh-my-zsh's `compinit` — end of `.zshrc` is safe. Before it, completions break.
- **bat paging**: `alias cat="bat"` pager-ifies long output and breaks scripts expecting cat semantics; use `bat --paging=never`.
- **Alias shadowing**: the block appends after any older alias sections, so eza wins over pre-existing `alias ls=...` — intended (mention it to the user, don't "fix" it).
- **Non-tty test noise**: `zsh -i -c` in a pipe shows a gitstatus/p10k "failed to initialize" error — false alarm from the missing tty, not a config problem.

## Verification (real shell, not memory)

```bash
# config valid
/Applications/Ghostty.app/Contents/MacOS/ghostty +validate-config && echo OK

# aliases + zoxide actually loaded (SHLVL=0 simulates a top-level shell so the
# fastfetch guard fires — proves startup behavior too)
env SHLVL=0 zsh -i -c 'whence -v ls; whence -v cat'
# expect:
# ls is an alias for eza -lao --git-repos --header --icons
# cat is an alias for bat --paging=never
```

fastfetch rendering in the test output itself is the positive signal for the startup hook.
