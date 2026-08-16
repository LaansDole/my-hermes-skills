---
name: tldr
description: "Use when the user asks for a TL;DR or before/after summary."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tldr, summary, recap, before-after, communication, concise]
---

# TL;DR — Structured Summary with Before/After Table

When the user asks "TL;DR", "summarize what you did", "what changed", "recap", or "before/after" — deliver a SCANNABLE structured summary, never a wall of prose. The user's baseline complaint (observed): TL;DRs came out as long text dumps; what they want is a compact summary plus a side-by-side comparison table.

## Format (follow exactly)

1. **One-line TL;DR** — the whole thing in a single sentence: what was done, on what, end state.
2. **Before/After table** — one row per meaningful axis of change. Columns: `| Aspect | BEFORE | AFTER |`. Use concrete facts (endpoint names, test counts, branch SHAs), not vague labels. Rows: 6-12 for a multi-part task; 2-4 for a small change.
3. **Open items / follow-ups** (only if non-empty) — short bullet list of what's still pending, so the reader knows the edge.

## Rules

- CONCISE: the user rejects long dumps. If the TL;DR + table exceeds ~40 lines, it's too long — cut rows, merge axes.
- Concrete over generic: "POST /recordings, GET /recordings/{id}" beats "new API endpoints". "229 tests pass (was 197)" beats "tests pass".
- Facts only: never invent numbers or states; if you didn't verify it, omit or mark it (e.g. "not verified on device").
- Terminal-friendly: plain text, pipe-table or aligned columns; no heavy markdown nesting, no MEDIA: tags.
- Security/breaking changes get their own row or a bolded line — those matter most to the reader.
- If nothing changed (e.g. "no action taken"), say so in the TL;DR line and skip the table.

## Example (shape)

TL;DR: Closed the mobile-app gap — defined one API contract, implemented it on both ends, code-reviewed, fixed 3 security holes, pushed both branches.

| Aspect | BEFORE | AFTER |
|---|---|---|
| Upload path | App -> GCS -> backend file_id | App POSTs multipart straight to backend |
| API | 5 old endpoints | /recordings CRUD contract |
| Tests | 197 unit | 229 unit + e2e integration |
| Security | path traversal + arbitrary write | allowlist + containment (review-verified) |
| Remote | nothing pushed | both feature branches pushed |

Open: HF_TOKEN for gated models; device UI verification (no Android SDK on this Mac).

## Common Mistakes

- **Prose dump** — exactly what the user rejected. If you catch yourself writing paragraphs, restructure into the table.
- **Too many rows** — every row must be a real axis of change; merge cosmetic rows.
- **Vague cells** — "improved", "fixed stuff", "better" are forbidden; state what concretely.
- **Inventing verification** — a test count or SHA you didn't confirm goes in the table only if actually run/verified.
