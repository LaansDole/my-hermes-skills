---
name: pbcopy-word-delivery
description: Deliver structured text content (verdicts, reports, summaries) directly to the macOS clipboard via pbcopy so the user can Cmd+V into Word without Warp terminal soft-wrap artifacts.
version: 1.0.0
metadata:
  hermes:
    tags: [clipboard, word, macos, pbcopy, formatting]
    requires_toolsets: [terminal]
---

# pbcopy Word Delivery

## When to use
Any time the user wants to paste structured content into Word (or any rich text app) and is using Warp terminal, where terminal column-width soft-wraps become hard newlines in the clipboard. Pipe content directly to pbcopy instead of printing it.

## Format rules (inside the piped content)
- Plain text only - no markdown symbols (no **, ##, ---, backticks, *, _)
- ALL CAPS for section headers (e.g. VERDICT, POPULATION - PASS)
- Single blank line between sections
- No hard line breaks mid-sentence - let Word wrap naturally
- Use a plain hyphen (-) for bullet points if needed

## Command pattern

```bash
printf '%s' "YOUR CONTENT HERE" | pbcopy && echo "Copied to clipboard."
```

Use printf '%s' (not echo) to avoid echo adding a trailing newline or interpreting escape sequences differently across shells.

For multi-line content with special characters (quotes, backslashes), write to a temp file first then pipe:

```bash
cat > /tmp/hermes_clip.txt << 'EOF'
YOUR CONTENT HERE
EOF
pbcopy < /tmp/hermes_clip.txt && echo "Copied to clipboard." && rm /tmp/hermes_clip.txt
```

Use the heredoc pattern when the content contains single quotes, since printf '%s' '...' cannot contain unescaped single quotes.

## Steps
1. Compose the full content as plain text following the format rules above.
2. Check if the content contains single quotes. If yes, use the heredoc pattern. If no, use printf '%s'.
3. Run the terminal command. Confirm with "Copied to clipboard." output.
4. Tell the user: content is in clipboard, ready for Cmd+V into Word.

## Pitfalls
- Single quotes inside printf '%s' '...' will break the shell quoting - use heredoc instead.
- echo adds a trailing newline and may interpret \n, \t on some shells - prefer printf.
- This is macOS-only (pbcopy). On Linux the equivalent is xclip -selection clipboard or xdotool.
- Do NOT also print the content to the terminal - the whole point is to avoid Warp rendering it.
