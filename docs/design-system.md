# cait-whisper Design System

> The visual language of cait-whisper as shipped (v2.5.6). The single source
> of truth in code is [`theme.py`](../theme.py); this document explains the
> intent behind those tokens. If a value here ever disagrees with `theme.py`,
> `theme.py` wins, and this doc should be corrected.

Direction: warm coral accent on a dark, editorial surface. Quiet at rest, with
a single hot color reserved for the moments that matter. Consistent across
every surface the app draws: the floating widget, the hover card, the
right-click menu, and the History / Dictionary / Pending / Settings window.

## How it's wired

`theme.py` holds every color, font, and spacing token. Both `client.py` and
`history_window.py` import from it. Change a value there, restart, and every
surface reflects it. Older code imports legacy aliases (`BG`, `FG`, `ACCENT`,
...) that map onto the brand tokens, so nothing has to be grep-replaced.

## Palette

### Ink family (dark surfaces)

| Token | Hex | Usage |
|-------|-----|-------|
| `INK` | `#15140F` | Primary background; widget coin fill; window bg |
| `INK_SOFT` | `#2A2620` | Elevated cards, hover-card surface, waveform glow |
| `INK_MUTE` | `#5A5448` | The standard border color; the resting coin ring + Φ |
| `INK_FAINT` | `#8B8676` | Captions, microcopy, the quiet "Resting" status |

### Paper family (light text on dark)

| Token | Hex | Usage |
|-------|-----|-------|
| `PAPER` | `#EFE7D2` | Primary text |
| `PAPER_WARM` | `#ECE4CF` | Slightly warmer text variant |
| `BONE` | `#F7F1DE` | High-contrast text on ink |

### Coral (the single hot brand color)

| Token | Hex | Usage |
|-------|-----|-------|
| `CORAL` | `#ED6F5C` | Brand mark, live recording, the coral period, primary action |
| `CORAL_SOFT` | `#F08E7C` | Hover state, processing/done/warming motion, ready flash |

### Jewelry / state

| Token | Hex | Usage |
|-------|-----|-------|
| `MUSTARD` | `#E9B94A` | Correction-watch pulse and "Waiting to learn" status (reserved) |
| `MUSTARD_SOFT` | `#FBD87A` | The brighter beat of the watch-pulse animation |
| `OLIVE` | `#6E7448` | Quiet third accent, low-priority use |
| `SUCCESS` | = `CORAL_SOFT` | Ready flash, dict-learned toast (brand-aligned, not green) |
| `WARNING` | = `MUSTARD` | Pending / watching |
| `INFO` | `#8FA3C9` | The one cool, non-brand accent: two-pass "better version" toast |
| `DANGER` | `#D16A4C` | Errors (within the coral family, but harsher) |

Rule: green is intentionally NOT in the palette. Success-style flashes use
`CORAL_SOFT` so the app never breaks character.

## The brand mark (Φ-in-circle)

The mark is a Greek capital Phi (Φ) centered in a ring. It is rendered with
PIL at 4x supersample then downsampled (LANCZOS) for crisp anti-aliasing at
any size, via `theme.render_mark_image()` / `theme.get_mark_photo()`. The same
renderer produces the multi-resolution `assets/cait.ico` and the tray icon.

The floating widget is clipped to an actual shape with `SetWindowRgn`: a circle
when idle, a stadium (pill) when active, so the resting coin appears to stretch
into the recording strip and back.

| Widget state | Fill | Ring + Φ |
|--------------|------|----------|
| PURE idle | `INK` (dark coin) | `INK_MUTE` (quiet gray) |
| COMMAND (sticky) | `CORAL` | `INK` Φ |
| COMMAND (one-shot armed) | `CORAL_SOFT` | `INK` Φ |
| Correction watch | `MUSTARD` ↔ `MUSTARD_SOFT` pulse | `INK` Φ |
| Ready (flash ~2s) | `CORAL_SOFT` | `INK` Φ |

Only live recording and sticky COMMAND use full-saturation `CORAL`. Everything
else stays quiet, so any shift to coral draws the eye.

## Wordmark

The product wordmark is "Cait. whisper", composed by `theme.brand_lockup()`:

- **Cait** - bold, brand sans (`FONT_FAMILY_TIGHT`)
- **.** - coral, italic serif, slightly larger (the one editorial accent)
- **whisper** - italic serif

A standalone coral period after section headings is available via
`theme.coral_period()`.

## Typography

The brand prefers Inter Tight / Playfair Display Italic / Inter / JetBrains
Mono. Most Windows machines have none of these, so `theme.resolve_fonts()`
detects-or-falls-back to Segoe UI / Georgia / Consolas at runtime. Type roles
(`t_caption` 8pt … `t_title` 13pt, `t_brand`, `t_mono`, `t_eyebrow`,
`t_wordmark`) are defined in `theme.py`.

Restraint: nothing larger than the title role for window content; the wordmark
is the only display-scale element. This is a utility app, not a marketing site.

## Spacing

A 4-pt grid. Tokens: `PAD_XS` 2, `PAD_SM` 4, `PAD_MD` 8, `PAD_LG` 12,
`PAD_XL` 16, `PAD_XXL` 24. Every surface uses multiples of 4.

## Borders

One color, two weights: `INK_MUTE` at `BORDER_MED` (2px) for floating chrome
(recording strip, hover card outline) and `BORDER_THIN` (1px) for inline
dividers (`theme.divider_frame()`). The border never communicates state; the
content color does.

## Custom glyphs

Inline icons are hand-drawn in PIL (not Unicode or emoji), so they share the
mark's anti-aliasing and brand language. `theme.get_glyph_photo(name, size,
color)` returns a cached PhotoImage. Available: transcripts, dictionary,
pending, settings, search, close, copy, arrow_right, plus, sparkle, trash, phi.
The history-window tabs and inline action buttons use these.

## Motion language

The widget speaks through motion, all in the coral family. States are
distinguished by HOW they move, not by hue:

| State | Color | Motion |
|-------|-------|--------|
| Warming up (startup) | `CORAL_SOFT` | calm symmetric breath while the model loads |
| Recording | `CORAL` | real FFT frequency spectrum, bass-center symmetric, reactive |
| Processing | `CORAL_SOFT` | organic multi-wave flow (incommensurate freqs, never visibly repeats) |
| Done | `CORAL_SOFT` | gather-to-center settle, then collapse to the coin |
| No speech | `INK_FAINT` | flat, near-silent, brief |

The recording waveform reacts to the actual spectral content of the voice and
rests flat during silence (RMS gate). A silence gate prevents background noise
from blooming the strip. The user can pick the visual style of the strip
(mirror bars default, plus filled wave, classic bars, dots, oscilloscope,
blocks) from the right-click Waveform menu.

Rules: minimal, no spinners, no bouncy easing. Editorial = controlled.

## Placement

The widget rests just above the taskbar and follows the cursor's monitor.
Placement (right-click menu) is bottom-center (default), bottom-right, or
bottom-left; the strip grows from the anchor (symmetric at center, leftward at
right, rightward at left). Manual drag overrides until the next placement pick
or monitor change.

## Surfaces

- **Widget**: dark coin / coral pill, brand mark, FFT waveform, hidden from the
  taskbar and Alt-Tab (it's a floating utility, not an app window).
- **Hover card**: `INK_SOFT` surface, `INK_MUTE` border. Brand lockup + live
  status pill (top-right), engine row, a two-column feature grid, and a
  "Last paste" section with the full wrapped text.
- **Right-click menu**: brand-styled via `_styled_menu()` - `INK` background,
  `PAPER` text, `CORAL` hover. (Earlier Tk-menu limitations were worked around;
  the menu is no longer OS-default gray.)
- **History window**: `INK` surface, coral tab glyphs, brand lockup in the
  title bar and OS title. Tabs: Recent / Dictionary / Pending / Settings.
- **Toasts**: `INK_SOFT` surface; foreground by meaning - `CORAL_SOFT` success,
  `MUSTARD` pending/watch, `INFO` two-pass, `DANGER` errors.

## What we deliberately don't do

- **No green.** Success is coral-soft.
- **No light mode.** Dark is the brand; the palette is dark-first by design.
- **No Electron/Tauri.** Tkinter keeps the install small; that constraint is a
  value, and the PIL-rendered mark + glyphs give us the polish we need within it.
