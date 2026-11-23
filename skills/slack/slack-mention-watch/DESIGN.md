---
name: slack-mention-watch dashboard
description: A low-glare "matte e-ink page" for watching Slack mentions, bot replies and the cron bot's state.
colors:
  light:
    paper: "#e9e6df"
    band: "#e1ddd4"
    wash: "#dcd7cc"
    rule: "#cdc8bd"
    edge: "#7d786d"
    track: "#817b6f"
    ink: "#2e2c29"
    ink-2: "#5b574f"
    accent: "#3d5a80"
    accent-hi: "#334c6d"
    on-accent: "#f3f1ec"
    fill: "#3d5a80"
    fill-hi: "#334c6d"
    on-fill: "#f3f1ec"
    hold: "#6f510f"
    ok: "#3f6247"
    err: "#8c3b2f"
  dark:
    paper: "#2b2a27"
    band: "#33322e"
    wash: "#3a3833"
    rule: "#47453f"
    edge: "#8a8579"
    track: "#807c72"
    ink: "#d9d4c9"
    ink-2: "#ada79b"
    accent: "#8fa9c9"
    accent-hi: "#a3b9d4"
    on-accent: "#23221f"
    fill: "#3e5878"
    fill-hi: "#425d7e"
    on-fill: "#d9d4c9"
    hold: "#d0a85a"
    ok: "#8db592"
    err: "#dc9585"
typography:
  ui:
    fontFamily: "-apple-system, BlinkMacSystemFont, Helvetica Neue, sans-serif"
    fontSize: "0.9375rem"
    lineHeight: 1.55
  read:
    fontFamily: "Charter, Iowan Old Style, Georgia, serif"
    fontSize: "1rem"
    lineHeight: 1.5
  mono:
    fontFamily: "ui-monospace, Menlo, Consolas, monospace"
    fontSize: "0.8125rem"
  state-sentence:
    fontFamily: "ui"
    fontSize: "1.375rem"
    fontWeight: 600
    lineHeight: 1.3
  small:
    fontSize: "0.8125rem"
  caps:
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.04em"
    textTransform: uppercase
rounded:
  control: "6px"
  code: "3px"
  skeleton: "2px"
spacing:
  side-desktop: "48px"
  side-mobile: "16px"
  breakpoint-mobile: "640px"
motion:
  state: "150ms ease-out"
  progress: "200ms ease-out"
  reduced: "none"
---

# slack-mention-watch dashboard: matte e-ink page

The page served by `scripts/dashboard.py`. It is a working tool (Operate mode) opened a few times a
day, often in the evening, so the whole system aims for low glare: it should read like an
e-reader page, with matte paper, soft ink and nothing shouting. It follows macOS light/dark through
`prefers-color-scheme`. There is no manual toggle.

This file documents this page only. The repo-root `DESIGN.md` covers the docs site.

## Colour

Both themes avoid `#000` and `#fff`. Dark mode is graphite, not near-black, and its ink is a warm
off-white at reduced luminance. Regions are told apart by flat tinted fields (paper, band, wash),
never by boxes or cards.

| Role | Light | Dark | Use |
|---|---|---|---|
| paper | #e9e6df | #2b2a27 | page ground |
| band | #e1ddd4 | #33322e | header band, raw-output and inline-code tint |
| wash | #dcd7cc | #3a3833 | hovered/focused row |
| rule | #cdc8bd | #47453f | 1px hairline dividers only |
| edge | #7d786d | #8a8579 | outlines of buttons and inputs |
| track | #817b6f | #807c72 | pause-progress track |
| ink / ink-2 | #2e2c29 / #5b574f | #d9d4c9 / #ada79b | text / secondary text |
| accent | #3d5a80 | #8fa9c9 | links, "Asks you" marker, focus ring |
| fill / on-fill | #3d5a80 / #f3f1ec | #3e5878 / #d9d4c9 | the one filled primary button |
| hold | #6f510f | #d0a85a | Paused state, progress fill and tick |
| ok | #3f6247 | #8db592 | Running state |
| err | #8c3b2f | #dc9585 | errors, Error marker |

In dark mode the primary fill is a deep slate with ink text instead of the pale accent. A pale fill
was the brightest area of the page and caused glare.

### Contrast (WCAG 2.x, computed from the tokens)

Light (on paper / band / wash):
- ink 11.17 / 10.27 / 9.70
- ink-2 5.77 / 5.30 / 5.01
- accent 5.67 / 5.21 / 4.92
- hold 5.89 / 5.42 / 5.12
- ok 5.53 / 5.08 / 4.80
- err 6.06 / 5.57 / 5.26
- edge 3.53 / 3.24 / 3.06 (UI boundary, 3:1)
- track 3.37 / 3.10 (sits on the band)
- on-fill on fill 6.26; on fill-hi 7.77

Dark (on paper / band / wash):
- ink 9.71 / 8.68 / 7.92
- ink-2 6.00 / 5.36 / 4.89
- accent 5.94 / 5.31 / 4.84
- hold 6.45 / 5.76 / 5.26
- ok 6.26 / 5.60 / 5.11
- err 5.93 / 5.30 / 4.84
- edge 3.90 / 3.49 / 3.18
- track 3.45 / 3.08
- on-fill on fill 4.95; on fill-hi 4.59

Every text pair passes AA 4.5:1, and every UI boundary passes 3:1. Hover on the dark primary only
goes one small step lighter, because a bigger step falls below 4.5:1.

## Type

- One system UI sans carries everything: chrome, state, tabs, labels and data. Body text is
  0.9375rem with line height 1.55.
- A system serif (Charter, Iowan Old Style, Georgia) is used only for mention text and bot-reply
  bodies, at 1rem with line height 1.5, so messages read like book text.
- Mono is used only for raw script output (live fetch) and inline code in replies. It is never
  decoration.
- Steps: 0.75rem caps (table heads, "Asks you"), 0.8125rem small text, 0.9375rem body and
  headings, 1rem reading text, and the 1.375rem/600 state sentence, which is the largest text on
  the page.
- Rank comes from weight and case rather than size. Times and counts use tabular numerals.
- No webfonts or external assets: the page is served by a stdlib script under a nonce CSP.

## Layout

- Full width. There are no max-width or reading-measure caps on containers or prose, by the
  owner's rule.
- Side padding is 48px on desktop and 16px at 640px or narrower.
- At 640px or narrower, list rows reflow into stacked records (sender and time, then source, then
  text). Header actions wrap below the state sentence, and the tab strip scrolls sideways.
- Nothing scrolls horizontally at 390px.

## Components

- **Header band** (one per watched job): the job name and schedule in small text, the state
  sentence ("Paused until Wed 25 Nov, 08:00" / "Paused" / "Running · next check HH:MM"), and a
  last-check line. While a job is paused, its stale next run time is never shown. Actions sit on the
  right.
- **Actions:** exactly one filled primary for the action that matters now (Resume now while
  paused, Pause while running). Pause until uses a datetime-local input. Cancel scheduled resume
  appears only when a helper job exists. All other controls are quiet 1px edge outlines with a 6px
  radius.
- **Pause-progress rule** (the signature): a 3px full-width track in `track`, filled with `hold` up
  to the elapsed share. A 2x9px `hold` tick marks the current point, so the rule reads as progress
  even near 0% or 100%. Labels: "Paused ..." on the left, time left in the centre, "Resumes ..." on
  the right (the centre label moves to its own row on mobile). The rule is hidden while running or
  when no resume is scheduled.
- **Tabs:** Notifications, Bot replies, Activity, Reviews, each with a count. They follow the
  ARIA tablist pattern, work from the keyboard, and keep their state in the URL hash. The active
  tab is ink at weight 600 with a 2px ink underline. On mobile, tabs have 10px horizontal padding
  so the focus ring clears the label.
- **Notifications:** an "Asks you" group comes first, then "Everything else", each newest first
  under a plain h3 heading with a count. There are no eyebrow labels. Rows use fixed columns:
  sender (600), source (ink-2), text (serif), and time flush right with an Open link. Identical
  messages from the same minute collapse into one row with a "sent twice" note (Open 1 / Open 2).
  "(no comment)" rows fold into one `<details>` line at the end.
- **Bot replies:** a date and model line, then the reply body rendered from light markdown
  (paragraphs, lists, inline code on the band tint, bold, https links). It is built from DOM nodes
  only, never innerHTML. A leading `[TAG]` is stripped from the text and shown as the Error word
  marker. A run's mentions sit in a `<details>`.
- **Activity:** counts as plain figures with labels, an Errors only toggle, and a hairline table.
  Status is always a word plus a colour, never colour alone.
- **States:** loading shows skeleton lines (2px radius), not spinners. Empty and error states are
  explicit sentences, never blank areas.

## Motion

Motion is used only for state changes: 150ms ease-out on background, border, colour and focus, and
200ms on the progress width. There are no entrance animations. Under
`prefers-reduced-motion: reduce`, every transition is off.

## Browser surfaces

`::selection`, `caret-color`, `accent-color`, `scrollbar-color` and `:focus-visible` rings (2px
accent, 2px offset) all come from the palette.

## Bans in this world

- No `#000` or `#fff`, and no saturated full-width colour blocks.
- No boxes or cards: hairlines and tinted fields only.
- No colour-only status.
- No eyebrow or kicker labels, no gradient text, and no glyph or emoji icons.
- No coloured side stripes wider than 1px, and no hard offset shadows.
