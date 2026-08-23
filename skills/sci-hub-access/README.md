# Sci-Hub / Sci-Net Access

Retrieve full text of paywalled papers via Sci-Hub mirrors, and join/use Sci-Net (sci-net.xyz) for post-2022 papers. Covers live-mirror discovery, the Turnstile browser gate, direct PDF fetch from the Sci-Hub CDN (`sci.bban.top`), and the Sci-Net invite-code API (`/invite/create` → `/invite/handle` → activation with `t.d` SCI tokens).

**Version**: 1.0.0  \
**Requires**: Hermes Agent, `browser` + `terminal` toolsets, `curl` + `python3` on `$PATH`

## One-time setup

1. Enable BOTH the `browser` and `terminal` toolsets:
   ```bash
   hermes tools list
   ```
   If `terminal` is missing, run `hermes setup tools` and enable Terminal / Shell Access.
2. Confirm `curl`, `python3`, and `pdftotext` (poppler) are available:
   ```bash
   curl --version | head -1 && python3 --version && which pdftotext
   ```
   On macOS: `brew install poppler` if `pdftotext` is missing.
3. No credentials needed. The browser flow uses the isolated `work` profile (Chrome, port 9250) — the skill never touches the user's daily Brave profile.

## Usage

Ask Hermes something like:

> "This DOI is paywalled, get me the PDF: 10.1007/978-3-031-93508-4_2"

or

> "It's a 2025 paper, not on Sci-Hub — walk me through the Sci-Net join."

The agent follows SKILL.md: Unpaywall check → direct CDN fetch → browser mirror flow → Sci-Net invite API + activation.

## Notes

- Papers published after ~2022 are NOT in Sci-Hub's database (publisher 2FA); Sci-Net is the route for those.
- Sci-Net registration requires a Phantom wallet + ≥0.035 SOL swapped to $SCI (~$5). The wallet transaction is always left to the user.
- Shadow-library access is for personal research reading; the Covidence upload workflow keeps these domains out of its pipeline by design.
