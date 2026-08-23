---
name: sci-hub-access
description: "Use when a paywalled DOI's full text is needed and no open-access copy exists — retrieving PDFs via Sci-Hub mirrors, and joining/using Sci-Net (sci-net.xyz) for post-2022 papers. Covers mirror discovery, direct PDF fetch, Turnstile gate, and the Sci-Net invite-code API."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [sci-hub, sci-net, paywall, full-text, doi, springer, elbakyan, pdf-retrieval, research-access]
---

# Sci-Hub / Sci-Net Access

## Overview

Two-tier access to paywalled papers:

- **Sci-Hub** — instant PDF for any DOI in its database. Works for papers
  published up to ~2022. PDFs are served from a CDN domain that needs no
  session at all.
- **Sci-Net** (`sci-net.xyz`) — Elbakyan's P2P request platform that fills the
  post-2022 gap (publisher 2FA broke Sci-Hub's credential harvesting). You
  request a paper with a bounty in $Sci-Hub (SCI) tokens; a community member
  uploads it; the PDF then enters Sci-Hub's DB for everyone.

**First check the legal route**: Unpaywall `is_oa: false` → no legal OA copy
exists → proceed here. Never substitute a lookalike paper.

## When is a paper actually on Sci-Hub?

Sci-Hub's DB is a frozen snapshot of ~a decade of credential-proxy downloads
(~88M docs, ~100 TB). Two conditions historically:

1. **Published before ~2022** — publishers rolled out 2FA in 2022, which broke
   Sci-Hub's automated login harvesting. The database effectively stops there.
   NEW papers enter only via Sci-Net requests (fulfilled uploads are added to
   Sci-Hub's DB for everyone).
2. **Someone with institutional access downloaded it through the proxy** —
   coverage is uneven. Not every pre-2022 paper is present.

Coverage factors (pre-2022): major publishers (Elsevier/Springer/IEEE/Wiley/
ACS/Nature) and major venues (LNCS, AAAI, NeurIPS) = near-total; small
national journals and workshop-only proceedings = spotty; famous/heavily-cited
papers ≈ always present; OA papers may be ABSENT (Sci-Hub stored what people
requested, not everything that exists); no-DOI items largely absent.

**Decision tree before spending time:**

| Paper | Expected outcome | Go to |
|---|---|---|
| Published after 2022 | not on Sci-Hub | Sci-Net flow (section 4) |
| Pre-2022, major publisher/venue | ~90%+ hit | direct CDN → mirror |
| Pre-2022, obscure venue | coin flip | one CDN attempt, then Sci-Net/author |
| Any year, small national journal | likely missing | author email / Sci-Net |

Ground truth is always the mirror: the not-found page ("Scientific mutual aid
community") is definitive — same DB on all mirrors, one check settles it.

## When to use

- A DOI is paywalled (Springer "preview of subscription content", IEEE "Sign
  in to Continue Reading", ScienceDirect captcha, etc.) and Unpaywall shows no
  OA copy.
- Paper published **after 2022** → it will NOT be in Sci-Hub's DB; go straight
  to the Sci-Net flow.
- Full text is needed for reading/review decisions (personal research use).
  The Covidence upload skill has its own hard backstop that excludes
  shadow-library domains — do not feed these URLs into Covidence uploads.

## Workflow

### 1. Verify no legal OA copy (30 s)

```bash
curl -s --max-time 20 "https://api.unpaywall.org/v2/${DOI}?email=<you@example.org>" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); loc=d.get('best_oa_location') or {}; print('is_oa:', d.get('is_oa')); print(loc.get('url_for_pdf') or loc.get('url') or 'NO OA URL')"
```

`is_oa: true` → use that URL. `is_oa: false` → continue.

### 2. Direct PDF fetch (fastest — no browser, no cookies)

Sci-Hub's PDF CDN serves `application/pdf` without the Turnstile cookie:

```bash
curl -sL --max-time 60 "https://sci.bban.top/pdf/${DOI}.pdf" -o paper.pdf
file paper.pdf   # expect: PDF document
pdftotext paper.pdf - | head -20
```

Verified 2026-08-23: `10.1038/s41586-020-2649-2` → HTTP 200, 1.2 MB, 9 pages.
If the CDN domain has rotated (404/empty), fall through to the browser flow.

### 3. Browser flow (mirror discovery + Turnstile)

1. **Find live mirrors** (2026-08-23: `.ee`, `.ren`, `.tf` alive; `.se`/`.st`/`.ru` dead):

   ```bash
   for d in sci-hub.ee sci-hub.ren sci-hub.tf sci-hub.se sci-hub.st sci-hub.ru; do
     printf '%-14s ' "$d"; curl -sL --max-time 8 -o /dev/null -w '%{http_code}\n' "https://$d/" 2>/dev/null || echo dead
   done
   ```

   Domain rotation happens often; check @ringo_ring (Elbakyan) or
   `t.me/s/scihubreal` for the current list.

2. **Open `https://<mirror>/<DOI>` in an ISOLATED browser profile** — never the
   user's daily Brave. Use the `work` profile (Chrome, port 9250) via
   `browser_profile(name='work')`.

3. **Turnstile gate**: the HTML pages sit behind Cloudflare Turnstile
   ("Verification - Sci-Hub"). In a real browser it auto-solves in ~2 s and
   sets a `scihub_verified` cookie (30-min TTL). curl cannot pass it — do not
   fight it with curl.

4. **Result page**: found papers render the citation + embedded PDF viewer.
   Not-found pages show "You can request this article through the Scientific
   mutual aid community" — that is the Sci-Net pointer.

5. **Extract text**: the viewer exposes no innerText — download the bytes
   (`sci.bban.top/pdf/<DOI>.pdf` from step 2, or the iframe URL) and run
   `pdftotext`.

### 4. Sci-Net join + invite code (for post-2022 papers)

**What the tokens are for** (before spending anything): the $Sci-Hub (SCI)
token is the platform's economy — it makes strangers upload papers for you.
Four jobs: (1) **bounty reward** — you attach a bounty (min 1 SCI) to a
request; a member uploads, you approve, they get paid; this replaced the old
automated harvesting. (2) **your balance, not a fee** — the activation payment
lands in your new account (send 12.83, account receives 12); it's
pre-funding, not a subscription. (3) **anti-spam gate** — accounts cost real
money, which blocks bot registration. (4) **project funding** — Elbakyan's
tokenomics sustains Sci-Hub/Sci-Net operations (PayPal froze donations in
2013; crypto is the channel that stayed open). You also EARN tokens by
fulfilling others' requests, so the balance can become self-sustaining.
Cost framing: ~$5 seed ≈ less than one €29.95 Springer chapter, and the
fulfilled paper enters Sci-Hub's DB for everyone. Caveat: young Solana token,
value can fluctuate; treat the seed as the price of a chapter.

**Prerequisites** (one-time, ~15 min, ~$5): Phantom wallet (phantom.com) →
buy ≥ 0.035 SOL → swap SOL → $SCI (in-app or `sci-net.xyz/exchange`).

1. **Generate invite code via API** (works headless — the web page's own JS
   does exactly these two POSTs):

   ```bash
   INVITE="some-8-to-64-char-sequence"
   curl -s -X POST "https://sci-net.xyz/invite/create" -H 'Content-Type: application/json' \
     -d "{\"invite\":\"$INVITE\"}"          # → {"success":true}
   curl -s -X POST "https://sci-net.xyz/invite/handle" -H 'Content-Type: application/json' \
     -d "{\"invite\":\"$INVITE\"}"          # → {"handle":null} … poll every 2-3 s
   # → {"handle":"P7M0UY8XQY09XYA9EY"}  (handle appears after a few seconds)
   ```

   UI alternative: `sci-net.xyz/invite/create`, type the sequence, click →.
   Note: the button only activates once the input is 8–64 chars.

2. **Activate** at `sci-net.xyz/invite/<handle>` — the page shows:
   - `x` = your invite sequence, `d` = your decimal identifier (e.g. `.83374118`)
   - Target wallet address (e.g. `5PgR6KisV7YQ3BmkuvHhvtfPSi7meBKUXrewNuq36SiX`)
   - **Send `t + d` SCI tokens** where `t` is any integer ≥ 8. Example: with
     `t=12`, send `12.83374118`; the account receives 12 tokens.
   - Scan the QR or send manually. **The decimal expires after 30 minutes** —
     if it lapses, just regenerate a fresh invite (free) and get a new `d`.

3. **Register** at `sci-net.xyz/join` — username + password, **no email**.

4. **Request a paper**: post DOI + bounty (min 1 SCI). If the DOI is already in
   Sci-Hub's DB the request auto-closes. Otherwise a member uploads within 30
   min, you approve, and the reward releases.

## Quick reference

| Task | Command / URL |
|---|---|
| Legal OA check | `api.unpaywall.org/v2/<DOI>?email=...` |
| Direct PDF | `curl -sL https://sci.bban.top/pdf/<DOI>.pdf -o paper.pdf` |
| Live mirror probe | loop over `sci-hub.ee .ren .tf .se .st .ru` |
| Browser profile | `browser_profile(name='work')` (never daily Brave) |
| Invite API | POST `/invite/create` → POST `/invite/handle` |
| Activate | `sci-net.xyz/invite/<handle>` → send `t.d` SCI (t ≥ 8) |
| Register | `sci-net.xyz/join` (no email) |

## Common mistakes

- **Chasing post-2022 papers on Sci-Hub** — they are not there (2FA era).
  Route to Sci-Net immediately; the not-found page says so.
- **Fighting Turnstile with curl** — the HTML gate is browser-only; only the
  PDF CDN is curl-friendly.
- **Using the daily browser profile** for shadow-library lookups — always the
  isolated `work` profile (9250); `brave-live` (9222) is the user's personal
  profile and off-limits.
- **Letting the 30-min decimal lapse** — regenerate; it costs nothing.
- **Clicking payment/wallet UI on the user's behalf** — stop at the QR/tx
  step and hand the transaction to the user.
- **browser_console CDP quirk**: it can attach to a stray new-tab target
  instead of the navigated page. Verify with
  `curl -s http://127.0.0.1:<port>/json/list` to see real targets, and rely
  on browser_navigate / browser_vision / browser_snapshot for state.

## Verification notes (2026-08-23)

- sci-hub.ee Turnstile auto-solved in the `work` profile; article page
  rendered citation + viewer for a 2020 Nature paper.
- sci.bban.top direct PDF fetch: 200, 1.2 MB, 9 pages, pdftotext clean.
- Sci-Net invite API: create → success, handle issued after ~3 s; activation
  page showed x, d, wallet address, and the t+d rule.
- Unpaywall on a 2025 Springer LNCS chapter: `is_oa: false` (no OA anywhere).
