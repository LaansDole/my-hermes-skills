# oh-my-ghostty

Hermes skill applying the [sudo-conner/oh-my-ghostty](https://github.com/sudo-conner/oh-my-ghostty) terminal stack on macOS: Ghostty theme config, fastfetch on every new terminal, and `cat`/`ls` replaced by bat/eza in zsh (zoxide initialized plain, no `cd` alias).

The upstream repo is a guide, not an installable framework — this skill turns it into a repeatable, idempotent setup with the gotchas fixed (Ghostty 1.3.1 theme naming, fastfetch `SHLVL` guard, zoxide init ordering, `bat --paging=never`).

Assumes Oh My Zsh + Powerlevel10k already configured; the skill never touches them.

## Install

```bash
ln -s ~/Projects/auto-learn-for-me/skills/productivity/oh-my-ghostty ~/.hermes/skills/productivity/oh-my-ghostty
```

## Use

Ask Hermes: "set up oh-my-ghostty", "add fastfetch on terminal startup", or "replace cat/ls with bat/eza". See `SKILL.md` for the full procedure and verification commands.
