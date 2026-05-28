# cait-whisper Design System (proposed v2.5.1+)

> Direction: warm terracotta accent, clean editorial layout. Consistent with Anthropic/Claude's visual language. Applied uniformly across every surface the app draws.

## Why this now

Current UI has drift:
- Main widget uses a **gray palette** (`#909090` idle, `#1A1A1C` active)
- Hover card uses a **gray palette** (`#1A1A1C`, `#CCCCCC`, `#888`)
- History & Dictionary window uses a **brown/tan palette** (`#18120E`, `#D4C4B0`, `#C87941`)
- Toast colors are ad-hoc (`#60D890` green, `#D4A060` amber, `#90B8E8` blue, `#E0C080`)
- Fonts are consistent (Segoe UI everywhere) but sizes are inconsistent per surface

The productivity panel (brown/tan) is already close to Claude's direction. The main widget and hover card are the outliers. This proposal unifies everything around the palette you already have, with tightened typography and consistent state feedback.

## Palette (single source of truth)

A new module `theme.py` holds the tokens. Every surface imports from it. One file change = global restyle.

### Surface

| Token | Hex | Usage |
|-------|-----|-------|
| `BG` | `#18120E` | Primary background (windows, widget active) |
| `BG_ELEVATED` | `#221810` | Input backgrounds, elevated surfaces |
| `BG_SUBTLE` | `#211713` | Hover states on BG |

### Text

| Token | Hex | Usage |
|-------|-----|-------|
| `FG` | `#D4C4B0` | Primary text |
| `FG_MUTED` | `#8A7A66` | Secondary text, labels |
| `FG_DIM` | `#5A4030` | Placeholder, disabled |

### Accent

| Token | Hex | Usage |
|-------|-----|-------|
| `ACCENT` | `#C87941` | Primary accent (terracotta). Used for: section headers, links, primary buttons, active tab indicator |
| `ACCENT_HOVER` | `#D48A52` | Hover on primary buttons |
| `ACCENT_DIM` | `#8F5E36` | Accent on muted surfaces |

### State

| Token | Hex | Usage |
|-------|-----|-------|
| `SUCCESS` | `#5FAD7A` | Ready toast, learned toast, "OK" status. Muted green that feels editorial, not industrial. |
| `WARNING` | `#D4A060` | Amber correction-watch pulse (stays) |
| `WARNING_BRIGHT` | `#FFC080` | Alternate amber for pulse |
| `INFO` | `#8FA3C9` | Two-pass "better version" toast. Cooler blue, still muted. |
| `DANGER` | `#D16A4C` | Error toasts, refused-save messages, hallucination warnings |

### Mode indicators

Dot color in each state. Replaces the current ad-hoc gray/blue mix.

| State | Color | Glyph |
|-------|-------|-------|
| PURE idle | `#8A7A66` (FG_MUTED) | `●` filled dot |
| COMMAND (sticky) | `#C87941` (ACCENT) | `◎` hollow ring |
| COMMAND (one-shot) | `#D48A52` (ACCENT_HOVER) | `◎` hollow ring |
| Correction watch | `#D4A060` ↔ `#FFC080` pulse | `●` |
| Ready (flash 2s) | `#5FAD7A` | `●` |
| Recording | Waveform animation over `BG` | - |

COMMAND-mode color now uses the brand terracotta instead of disconnected blue. Unified visual language.

## Typography

Single family: **Segoe UI** (Windows native). No new fonts.

| Role | Size | Weight | Usage |
|------|------|--------|-------|
| `TEXT_BODY` | 9pt | normal | Standard body text, menu items |
| `TEXT_SMALL` | 8pt | normal | Helper text, toasts, footers |
| `TEXT_CAPTION` | 7pt | normal | Inline help below inputs |
| `TEXT_LABEL` | 9pt | normal | Form field labels |
| `TEXT_HEADING` | 10pt | bold | Section headings within tabs |
| `TEXT_TITLE` | 11pt | bold | Window titles |
| `TEXT_MONO` | 9pt | - | Code, file paths, config values (Consolas) |

No size smaller than 7pt. No size larger than 11pt. This is a utility app, not a marketing site - editorial restraint means NOT going big.

## Spacing

The editorial look comes from **generous consistent whitespace**, not from big elements.

| Token | Value | Usage |
|-------|-------|-------|
| `PAD_XS` | 2px | Tight row padding |
| `PAD_SM` | 4px | Inside toasts, between related rows |
| `PAD_MD` | 8px | Default component padding, between groups |
| `PAD_LG` | 12px | Window edge padding, section separators |
| `PAD_XL` | 20px | Section indent, major separators |
| `PAD_XXL` | 16px | Vertical rhythm between major sections |

One rule: every surface uses multiples of 4. No ad-hoc "3px here, 5px there".

## Border / divider rule

Use horizontal 1px-tall `Frame` at `FG_DIM` as a divider between sections (already the pattern in `history_window.py`). Don't use `tk.Separator` inconsistently.

## Component-level changes

### 1. Widget dot + active state

Today:
- Idle: gray dot on gray
- Active: darker gray rectangle with white border

Proposed:
- Idle: FG_MUTED dot (subtle brown-gray) on transparent root
- Active (recording): BG_ELEVATED rectangle with 1px ACCENT border
- Keeps the existing DWM rounded corners on Windows 11

One specific fix: the **active_border_color** in `config.example.json` is currently `#CCCCCC` (cold gray). Change to `ACCENT` so recording state shares the terracotta language with everything else.

### 2. Hover card (currently cold gray)

Today: `#1A1A1C` bg, `#CCCCCC` heading, `#888` labels, `#DDDDDD` values.
Proposed: `BG` bg, `ACCENT` heading, `FG_MUTED` labels, `FG` values. Bring it into the editorial family.

Specifically this line is the change:
```python
tk.Label(frame, text="cait-whisper", bg="#1A1A1C", fg="#CCCCCC", ...)
# becomes
tk.Label(frame, text="cait-whisper", bg=theme.BG, fg=theme.ACCENT, ...)
```

### 3. Right-click menu

Tk's native Menu is mostly uncustomizable (it uses the OS theme). Where we CAN influence: first-item "cait-whisper" title uses ACCENT, separators match, disabled items use FG_DIM. Accept that the OS styles the rest.

### 4. Toast styles

Current ad-hoc toasts (dict-learned, two-pass, pending-correction) all have different color combinations. Unify:

| Toast | BG | FG | Border accent |
|-------|-----|-----|---------------|
| Success (dict learned, ready, model switch) | BG | SUCCESS | SUCCESS |
| Warning (pending correction, hallucination) | BG | WARNING | WARNING |
| Info (two-pass better version) | BG | INFO | INFO |
| Danger (errors) | BG | DANGER | DANGER |

All use 1px border in the accent color, 6px padding, Segoe UI 8pt.

### 5. Settings tab (the new v2.5.0 surface)

Already uses the brown/tan palette via `_BG`, `_FG`, `_ACC`, `_DIM` imports from history_window. Will migrate to `theme.py` tokens as part of the consolidation. Visual result: identical (the history_window palette IS the target palette).

### 6. Dictionary / History / Pending tabs

Already use the palette. No visual change; just import from `theme.py` instead of the local `_BG`, `_FG` constants.

## Motion

Keep motion minimal. Editorial = still.

Rules:
- **Dot pulse** (correction watch) already done correctly. Stays.
- **Ready flash** (green for 2s) stays.
- **Dict-learned toast** slides in/out in 250ms (subtle fade via `attributes("-alpha", ...)` if we want to be fancier; optional).
- **No spring animations.** No bouncy easings. One "ease" curve at most.
- **No spinners.** If we need a "thinking" indicator, the hover card can show "Testing..." as text, nothing more.

## Implementation plan

### Phase 1: Create `theme.py` (before any UI change)

```python
# theme.py
# Single source of truth for every color, spacing, and font token cait-whisper uses.
# Update a value here -> restart -> every surface reflects it.

# Surface
BG            = "#18120E"
BG_ELEVATED   = "#221810"
BG_SUBTLE     = "#211713"

# Text
FG            = "#D4C4B0"
FG_MUTED      = "#8A7A66"
FG_DIM        = "#5A4030"

# Accent
ACCENT        = "#C87941"
ACCENT_HOVER  = "#D48A52"
ACCENT_DIM    = "#8F5E36"

# State
SUCCESS       = "#5FAD7A"
WARNING       = "#D4A060"
WARNING_BRIGHT = "#FFC080"
INFO          = "#8FA3C9"
DANGER        = "#D16A4C"

# Typography
FONT_FAMILY   = "Segoe UI"
FONT_MONO     = "Consolas"

TEXT_BODY     = (FONT_FAMILY, 9)
TEXT_SMALL    = (FONT_FAMILY, 8)
TEXT_CAPTION  = (FONT_FAMILY, 7)
TEXT_LABEL    = (FONT_FAMILY, 9)
TEXT_HEADING  = (FONT_FAMILY, 10, "bold")
TEXT_TITLE    = (FONT_FAMILY, 11, "bold")
TEXT_MONO     = (FONT_MONO, 9)

# Spacing (multiples of 4)
PAD_XS = 2
PAD_SM = 4
PAD_MD = 8
PAD_LG = 12
PAD_XL = 20
PAD_XXL = 16  # vertical section rhythm
```

### Phase 2: Migrate history_window.py (lowest risk)

Already uses the palette - rename `_BG` -> `theme.BG`, etc. No visual change, just consolidation.

### Phase 3: Migrate client.py widget and hover card

The bigger change. Replace `_IDLE_COLOR`, `_BG_ACTIVE`, hardcoded toast colors with theme tokens. Update `config.example.json`'s `appearance.active_border_color` default to use `ACCENT`.

Config backward compat: users who set custom appearance values keep them. Users on defaults pick up the new ACCENT border.

### Phase 4: Update toasts

The three toast methods (`_notify_dict_learned`, `_notify_bg_transcription`, `_notify_dict_pending`) share a common structure - extract into a single `_show_toast(text, style)` helper where style is SUCCESS/WARNING/INFO/DANGER. Each toast shrinks from ~10 lines to ~3.

### Phase 5: Verify in dark mode and multi-monitor

Light mode isn't in scope - cait-whisper is dark-first. If a user runs Windows in light mode, the terracotta-on-dark remains readable and intentional. Same palette either way.

## Where this lands

Proposal: ship as **v2.5.2** (after v2.5.1's timezone + commands). Rationale:

- v2.5.0 is code-level, no visible restyling. Ships first.
- v2.5.1 adds the timezone tab and command list — NEW surfaces that would benefit from the theme. BUT those are ambitious on their own.
- v2.5.2 is pure restyling, no new features. Low risk. Clean commit. Easy rollback if anything looks off.

Alternative: fold the restyle into v2.5.1 so new surfaces land with the final palette and we don't restyle twice. More scope but fewer commits. Acceptable if v2.5.0 passes UAT cleanly.

## What I'm NOT proposing

- **Not changing the dot shape/size.** The filled/hollow glyph pair (`●` / `◎`) is the best signal we have in this space. Keep it.
- **Not replacing Tkinter.** Migrating to Electron/Tauri would give us 10x more design flexibility but also 10x the install footprint. Out of scope forever unless we abandon "small Python install" as a value.
- **Not adding a light mode toggle.** Dark is the brand. Users can't flip it. We save the complexity.
- **Not redesigning the right-click menu.** Tk menus use OS theme; we can't meaningfully restyle them without native-widget heroics.

## What happens next

1. You finish v2.5.0 UAT, I commit/ship if it passes.
2. You review this design doc between runs. Edit or approve.
3. We ship v2.5.1 (timezones + commands) using the target palette.
4. Optional v2.5.2 is pure theme consolidation (depends on how much drift v2.5.1 leaves).
