"""cait-whisper design tokens.

Single source of truth for color, typography, and spacing across every
Tkinter surface the app draws (widget mark, hover card, right-click menu,
history/dictionary/pending/settings panel).

Adapted from the Cait brand system (Atelier Zero). The hellocait.com
website is light/ivory; cait-whisper is the BRAND MARK's dark-backdrop
context applied to a desktop overlay. Same color tokens, inverted surface.

Change a value here, restart, and every surface that imports from this
module reflects it.
"""

from __future__ import annotations

import tkinter.font as tkfont

# ─── Brand palette ────────────────────────────────────────────────────────
# Lifted verbatim from the brand system. Do not invent new hex.

# Ink family (dark surfaces - we're the inverse-surface context)
INK            = "#15140f"   # Primary background. Darkest allowed value.
INK_SOFT       = "#2a2620"   # Secondary surface, elevated cards
INK_MUTE       = "#5a5448"   # Borders, dividers, disabled
INK_FAINT      = "#8b8676"   # Captions, microcopy, page-number gray

# Paper family (light text on dark - inverted from the website usage)
PAPER          = "#efe7d2"   # Primary text
PAPER_WARM     = "#ece4cf"   # Slightly warmer text variant
BONE           = "#f7f1de"   # High-contrast surface element on Ink

# Accent (single hot color, used sparingly)
CORAL          = "#ed6f5c"   # Brand coral. CTAs, brand mark, coral period
CORAL_SOFT     = "#f08e7c"   # Hover state for coral elements

# Jewelry / quiet accents
MUSTARD        = "#e9b94a"   # Reserved for "watching" / correction-watch pulse
MUSTARD_SOFT   = "#fbd87a"   # Brighter beat for the watch-pulse animation
OLIVE          = "#6e7448"   # Quiet third accent. Low-priority toasts.

# State signals (kept distinct from brand jewelry)
# Green is intentionally NOT in the brand palette - we use coral-soft for
# success-style flashes instead to stay on brand.
SUCCESS        = CORAL_SOFT  # "model ready" pulse, dict-learned flash
DANGER         = "#d16a4c"   # Errors. Within coral family but harsher.
WARNING        = MUSTARD     # Pending state, correction-watch
INFO           = "#8fa3c9"   # Two-pass "better version available" - cool, non-brand

# ─── Aliased legacy names ────────────────────────────────────────────────
# Older code imports BG / FG / FG_DIM / etc. Keep these as aliases so we
# don't have to grep-and-replace every reference.
BG             = INK
BG_ELEVATED    = INK_SOFT
BG_SUBTLE      = "#1c1a14"
FG             = PAPER
FG_MUTED       = INK_FAINT
FG_DIM         = INK_MUTE
ACCENT         = CORAL
ACCENT_HOVER   = CORAL_SOFT
ACCENT_DIM     = OLIVE

# Borders for active vs inactive cards
ACTIVE_BORDER_COLOR   = CORAL
INACTIVE_BORDER_COLOR = INK_MUTE

# Background tints (consistent low alpha overlay)
BORDER_THIN = 1
BORDER_MED  = 2


# ─── Typography ───────────────────────────────────────────────────────────
# Brand specifies Inter Tight / Playfair Display Italic / Inter / JetBrains Mono.
# Most Windows machines have NONE of these by default. We detect-or-fallback
# so the app renders correctly everywhere without forcing a download.

def _first_available_font(candidates: list[str], default: str) -> str:
    """Return the first font in `candidates` that's actually installed.
    Falls back to `default`. Safe to call after Tk root is created."""
    try:
        installed = set(tkfont.families())
        for c in candidates:
            if c in installed:
                return c
    except Exception:
        pass
    return default


# These are filled in lazily once a Tk root exists. Until then, the module
# returns Segoe UI / Consolas defaults so imports don't require a Tk context.
FONT_FAMILY        = "Segoe UI"
FONT_FAMILY_TIGHT  = "Segoe UI"
FONT_FAMILY_ITALIC = "Segoe UI"
FONT_MONO          = "Consolas"


def resolve_fonts():
    """Call once after a Tk root exists to upgrade font choices if better
    options are installed. Idempotent. Safe to skip - defaults are fine."""
    global FONT_FAMILY, FONT_FAMILY_TIGHT, FONT_FAMILY_ITALIC, FONT_MONO
    FONT_FAMILY        = _first_available_font(["Inter", "Segoe UI"], "Segoe UI")
    FONT_FAMILY_TIGHT  = _first_available_font(["Inter Tight", "Inter", "Segoe UI"], "Segoe UI")
    FONT_FAMILY_ITALIC = _first_available_font(
        ["Playfair Display", "Georgia", "Segoe UI"], "Segoe UI"
    )
    FONT_MONO          = _first_available_font(
        ["JetBrains Mono", "Cascadia Mono", "Consolas"], "Consolas"
    )


# Type roles. Cap sizes at 14pt for window content; 22pt for the brand
# wordmark in the title strip. Larger sizes from the brand spec (38-200px)
# don't apply to a utility window.

def t_caption():  return (FONT_FAMILY,        8)
def t_small():    return (FONT_FAMILY,        9)
def t_body():     return (FONT_FAMILY,        10)
def t_label():    return (FONT_FAMILY,        10)
def t_heading():  return (FONT_FAMILY_TIGHT,  11, "bold")
def t_title():    return (FONT_FAMILY_TIGHT,  13, "bold")
def t_brand():    return (FONT_FAMILY_ITALIC, 14, "italic")
def t_mono():     return (FONT_MONO,          9)
def t_mono_sm():  return (FONT_MONO,          8)
def t_eyebrow():
    """Brand 'eyebrow' microcopy - 9pt uppercase tracked, used above section
    headings as the small all-caps label."""
    return (FONT_FAMILY_TIGHT, 8, "bold")

def t_wordmark():
    """The 'Cait' wordmark itself: BOLD, brand sans (Inter Tight / Segoe UI).
    Per the user's brand override: wordmark is bold (not italic), and only
    the trailing coral period is italic. Pair this with coral_period() to
    render the full 'Cait.' lockup with brand-correct emphasis."""
    return (FONT_FAMILY_TIGHT, 14, "bold")


# Back-compat constants for older import sites
TEXT_BODY     = (FONT_FAMILY, 9)
TEXT_SMALL    = (FONT_FAMILY, 8)
TEXT_CAPTION  = (FONT_FAMILY, 7)
TEXT_LABEL    = (FONT_FAMILY, 9)
TEXT_HEADING  = (FONT_FAMILY, 10, "bold")
TEXT_TITLE    = (FONT_FAMILY, 11, "bold")
TEXT_MONO_BODY = (FONT_MONO, 9)
TEXT_MONO_SMALL = (FONT_MONO, 8)


# ─── Spacing (multiples of 4, brand 8px baseline) ────────────────────────

PAD_XS  = 2
PAD_SM  = 4
PAD_MD  = 8
PAD_LG  = 12
PAD_XL  = 16
PAD_XXL = 24


# ─── Helpers ─────────────────────────────────────────────────────────────

def divider_frame(parent, bg=None):
    """1-pixel-tall horizontal divider. Used between sections.
    Pack with `fill="x"`."""
    import tkinter as tk
    return tk.Frame(parent, bg=(bg or INK_MUTE), height=BORDER_THIN)


def coral_period(parent, font=None):
    """A single coral period for use after section H1/H2 headings.
    Brand rule: italic serif, coral, one per viewport. Returns a tk.Label
    you pack with `side='left'` right after the heading label.

    Usage:
        tk.Label(row, text="Settings", ...).pack(side="left")
        theme.coral_period(row).pack(side="left")
    """
    import tkinter as tk
    return tk.Label(
        parent,
        text=".",
        bg=parent.cget("bg") if hasattr(parent, "cget") else INK,
        fg=CORAL,
        font=font or (FONT_FAMILY_ITALIC, 14, "italic", "bold"),
        padx=0, pady=0,
    )


def brand_lockup(parent, *, bg=None, fg=None,
                 cait_size: int = 14, period_size: int = 16,
                 whisper_size: int = 14):
    """The full 'Cait. whisper' brand lockup as a packed Frame.

    Composes three labels in a horizontal row:
        Cait     - BOLD, brand sans (Inter Tight / Segoe UI fallback)
        .        - CORAL, italic brand serif, slightly larger
        whisper  - italic, brand serif, same color as Cait

    The lockup is the canonical product wordmark. Use it anywhere the
    product needs to identify itself: hover card, settings header,
    history window title bar.

    Args:
        parent:       parent widget
        bg:           background color; defaults to parent's bg if available
        fg:           color for "Cait" and "whisper" (default PAPER)
        cait_size:    point size for "Cait" (default 14)
        period_size:  point size for "." (slightly larger reads as accent)
        whisper_size: point size for "whisper"

    Returns:
        tk.Frame - pack it as you would a single label.
    """
    import tkinter as tk
    if bg is None:
        try:
            bg = parent.cget("bg")
        except Exception:
            bg = INK
    if fg is None:
        fg = PAPER

    container = tk.Frame(parent, bg=bg)
    tk.Label(container, text="Cait", bg=bg, fg=fg,
             font=(FONT_FAMILY_TIGHT, cait_size, "bold"),
             padx=0, pady=0).pack(side="left")
    tk.Label(container, text=".", bg=bg, fg=CORAL,
             font=(FONT_FAMILY_ITALIC, period_size, "italic", "bold"),
             padx=0, pady=0).pack(side="left")
    tk.Label(container, text=" whisper", bg=bg, fg=fg,
             font=(FONT_FAMILY_ITALIC, whisper_size, "italic"),
             padx=0, pady=0).pack(side="left")
    return container


# ─── PIL-based brand mark + custom glyphs ─────────────────────────────────
#
# Tk Canvas's `create_oval` does NOT anti-alias on Windows. At small sizes
# the brand mark renders as a jagged pink blob (the AA edges have nothing
# solid to blend against under -transparentcolor). Fix: render via PIL at
# 4x supersample then downsample with LANCZOS. PIL is already a dependency
# (Pillow ships with the tray icon code), so this is pure win.
#
# All rendering helpers return a PIL Image. Callers convert to PhotoImage
# (via PIL.ImageTk.PhotoImage) and keep a reference on their widget so the
# image doesn't get garbage-collected out from under Tk.

# Common bold font candidates that ship on Windows. PIL's truetype loader
# searches C:\Windows\Fonts and a few other system paths automatically when
# given just the filename. Falls through to the next candidate on miss.
_BOLD_FONT_PATHS = [
    "InterTight-Bold.ttf",
    "Inter-Bold.ttf",
    "seguibl.ttf",     # Segoe UI Black (heaviest weight)
    "seguibld.ttf",    # Segoe UI Semibold
    "segoeuib.ttf",    # Segoe UI Bold
    "arialbd.ttf",     # Arial Bold
]


def _load_bold_font(px_size: int):
    """Find the best available bold sans font at the given pixel size.
    Returns a PIL ImageFont. Falls back to the default bitmap font on miss.
    """
    from PIL import ImageFont
    for path in _BOLD_FONT_PATHS:
        try:
            return ImageFont.truetype(path, px_size)
        except Exception:
            continue
    return ImageFont.load_default()


def render_mark_image(size: int, *, border_color: str = CORAL,
                      glyph_color: str = CORAL, fill_color: str | None = None,
                      supersample: int = 4):
    """Render the cait brand mark (Φ-in-circle) as a PIL RGBA Image.

    Renders at `size * supersample` then LANCZOS-downsamples to `size` for
    smooth anti-aliased edges. The result is a transparent-background image
    you can paste anywhere via tk.Label(image=...) or canvas.create_image().

    Visual recipe:
      - 12% inset around the ring (more breathing room than v2.5.1)
      - ring stroke = size / 14 (heavier than Canvas version, reads clean
        even at 16px once supersampled)
      - Φ at 52% of total size, centered, in a bold sans
      - optional dark fill inside the ring (the 'coin' look)

    Args:
        size: final pixel dimension (image is `size x size`)
        border_color: ring color
        glyph_color: Φ text color
        fill_color: inner disc color, or None for transparent center
        supersample: render at N× size before downsampling. 4 is the sweet
            spot; higher costs memory without visible benefit.
    """
    from PIL import Image, ImageDraw

    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    inset = int(s * 0.12)
    box = [inset, inset, s - inset, s - inset]
    stroke = max(supersample, s // 14)

    # 1) Filled disc (the dark INK coin in PURE idle, the coral fill in
    #    COMMAND mode, etc.)
    if fill_color:
        d.ellipse(box, fill=fill_color)

    # 2) Ring stroke. PIL's ellipse outline+width draws a properly anti-
    #    aliased ring at supersample resolution.
    d.ellipse(box, outline=border_color, width=stroke)

    # 3) Φ glyph at center. Optical centering: a tiny vertical nudge so the
    #    bowl visually sits in the middle (Φ has more weight at the bowl
    #    than at the tail).
    phi_px = int(s * 0.52)
    font = _load_bold_font(phi_px)
    try:
        bbox = d.textbbox((0, 0), "Φ", font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (s - tw) // 2 - bbox[0]
        ty = (s - th) // 2 - bbox[1] - int(s * 0.01)
    except Exception:
        tx = ty = s // 4
    d.text((tx, ty), "Φ", fill=glyph_color, font=font)

    return img.resize((size, size), Image.LANCZOS)


def render_glyph(name: str, size: int, color: str, supersample: int = 4):
    """Render a custom brand glyph as a PIL RGBA Image.

    These are bespoke vector-style icons drawn from primitives so they share
    a visual language with the brand mark. Each is a single-color silhouette
    on a transparent background, designed to read at 14-20px.

    Available glyphs:
      'transcripts'  - three stacked horizontal lines, paragraph-like
      'dictionary'   - book: vertical spine + two page-lines
      'pending'      - hourglass outline with crossing lines
      'settings'     - three sliders with offset thumbs
      'search'       - magnifier circle + diagonal handle
      'close'        - clean ×, rounded line caps
      'plus'         - +
      'arrow_right'  - small → for "heard → corrected" rows
      'sparkle'      - 4-point star, used for AI/two-pass cues
      'copy'         - two overlapping squares
      'trash'        - simple bin silhouette
    """
    from PIL import Image, ImageDraw

    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    stroke = max(2, s // 14)
    cap_r = stroke / 2  # rounded line caps use this radius

    def _line(p1, p2):
        """Anti-aliased line with rounded caps (PIL doesn't natively round
        line ends, so we add circle caps at each endpoint)."""
        d.line([p1, p2], fill=color, width=stroke)
        d.ellipse([p1[0] - cap_r, p1[1] - cap_r,
                   p1[0] + cap_r, p1[1] + cap_r], fill=color)
        d.ellipse([p2[0] - cap_r, p2[1] - cap_r,
                   p2[0] + cap_r, p2[1] + cap_r], fill=color)

    if name == "transcripts":
        # Three lines of varying length, evoking lines of body copy
        margin = int(s * 0.20)
        gap    = int(s * 0.14)
        line_h = stroke
        lengths = [0.78, 0.62, 0.72]
        y = margin
        for ratio in lengths:
            x1 = margin
            x2 = int(margin + (s - 2 * margin) * ratio)
            d.rounded_rectangle([x1, y, x2, y + line_h],
                                radius=line_h // 2, fill=color)
            y += line_h + gap

    elif name == "dictionary":
        # Book: solid spine on the left + two horizontal "page lines"
        margin = int(s * 0.20)
        spine_w = stroke * 2
        d.rounded_rectangle([margin, margin, margin + spine_w, s - margin],
                            radius=spine_w // 2, fill=color)
        # Two page lines to the right of the spine
        page_x = margin + spine_w + int(s * 0.10)
        line_h = stroke
        gap    = int(s * 0.18)
        y = margin + int(s * 0.08)
        for ratio in (0.72, 0.55):
            x2 = int(page_x + (s - margin - page_x) * ratio)
            d.rounded_rectangle([page_x, y, x2, y + line_h],
                                radius=line_h // 2, fill=color)
            y += line_h + gap

    elif name == "pending":
        # Hourglass outline. Two horizontal bars at top/bottom, two diagonal
        # lines crossing to form the pinch.
        margin = int(s * 0.22)
        top_y  = margin
        bot_y  = s - margin
        left   = margin
        right  = s - margin
        d.rounded_rectangle([left, top_y, right, top_y + stroke],
                            radius=stroke // 2, fill=color)
        d.rounded_rectangle([left, bot_y - stroke, right, bot_y],
                            radius=stroke // 2, fill=color)
        _line((left, top_y), (right, bot_y))
        _line((right, top_y), (left, bot_y))

    elif name == "settings":
        # Three horizontal sliders with thumbs at different positions.
        # Reads as "tuning" - more brand-distinct than a gear cliché.
        margin = int(s * 0.20)
        track_h = max(2, stroke - supersample)   # thin track
        thumb_r = stroke + supersample
        gap = int(s * 0.18)
        positions = [0.65, 0.30, 0.78]
        y = margin + thumb_r
        for pos in positions:
            # Track
            d.rounded_rectangle([margin, y - track_h // 2,
                                 s - margin, y + track_h // 2],
                                radius=track_h // 2, fill=color)
            # Thumb
            tx = int(margin + (s - 2 * margin) * pos)
            d.ellipse([tx - thumb_r, y - thumb_r,
                       tx + thumb_r, y + thumb_r], fill=color)
            y += thumb_r * 2 + gap

    elif name == "search":
        # Magnifier: ring + diagonal handle from bottom-right of ring
        ring_inset = int(s * 0.18)
        ring_size  = int(s * 0.50)
        ring_box = [ring_inset, ring_inset,
                    ring_inset + ring_size, ring_inset + ring_size]
        d.ellipse(ring_box, outline=color, width=stroke)
        # Handle starts at 45° on the ring and extends to bottom-right corner
        import math
        cx = ring_inset + ring_size // 2
        cy = ring_inset + ring_size // 2
        r  = ring_size // 2
        ang = math.pi / 4
        h1 = (cx + r * math.cos(ang), cy + r * math.sin(ang))
        h2 = (s - int(s * 0.15), s - int(s * 0.15))
        _line(h1, h2)

    elif name == "close":
        # Clean × with rounded caps
        m = int(s * 0.26)
        _line((m, m), (s - m, s - m))
        _line((s - m, m), (m, s - m))

    elif name == "phi":
        # Standalone Φ rendered via PIL text. Used as the submit button
        # in the recording strip so it shares the exact same anti-aliasing
        # pipeline as the close glyph next to it. Bold sans, optically
        # centered with a small vertical nudge so the bowl sits visually
        # on the same baseline as a paired '×'.
        phi_px = int(s * 0.85)
        font = _load_bold_font(phi_px)
        try:
            bbox = d.textbbox((0, 0), "Φ", font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
            tx = (s - tw) // 2 - bbox[0]
            ty = (s - th) // 2 - bbox[1] - int(s * 0.02)
        except Exception:
            tx = ty = s // 6
        d.text((tx, ty), "Φ", fill=color, font=font)

    elif name == "plus":
        m = int(s * 0.22)
        # Horizontal
        d.rounded_rectangle([m, s // 2 - stroke // 2,
                             s - m, s // 2 + stroke // 2],
                            radius=stroke // 2, fill=color)
        # Vertical
        d.rounded_rectangle([s // 2 - stroke // 2, m,
                             s // 2 + stroke // 2, s - m],
                            radius=stroke // 2, fill=color)

    elif name == "arrow_right":
        # Slim arrow used in dict rows ("heard → corrected")
        m   = int(s * 0.20)
        mid = s // 2
        # Shaft
        d.rounded_rectangle([m, mid - stroke // 2,
                             s - m - stroke, mid + stroke // 2],
                            radius=stroke // 2, fill=color)
        # Head: two diagonal lines from tip
        tip_x = s - m
        head_len = int(s * 0.22)
        _line((tip_x, mid), (tip_x - head_len, mid - head_len))
        _line((tip_x, mid), (tip_x - head_len, mid + head_len))

    elif name == "sparkle":
        # 4-point star: two perpendicular tapered diamonds
        cx, cy = s // 2, s // 2
        m = int(s * 0.18)
        thick = int(s * 0.08)
        # Vertical diamond
        d.polygon([(cx, m), (cx + thick, cy),
                   (cx, s - m), (cx - thick, cy)], fill=color)
        # Horizontal diamond
        d.polygon([(m, cy), (cx, cy - thick),
                   (s - m, cy), (cx, cy + thick)], fill=color)

    elif name == "copy":
        # Two overlapping rounded squares
        size_sq = int(s * 0.50)
        off = int(s * 0.10)
        m   = int(s * 0.18)
        # Back square (outline)
        d.rounded_rectangle([m + off, m + off,
                             m + off + size_sq, m + off + size_sq],
                            radius=stroke, outline=color, width=stroke)
        # Front square (filled background to "overlap" then re-outlined)
        front = [m, m + int(s * 0.04),
                 m + size_sq, m + int(s * 0.04) + size_sq]
        d.rounded_rectangle(front, radius=stroke,
                            outline=color, width=stroke)

    elif name == "trash":
        # Simple bin: lid + body + two slats
        m = int(s * 0.20)
        lid_y = m + int(s * 0.04)
        body_top = lid_y + int(s * 0.12)
        # Handle hump
        hx1 = m + int(s * 0.20)
        hx2 = s - m - int(s * 0.20)
        d.rounded_rectangle([hx1, m, hx2, lid_y],
                            radius=stroke // 2, fill=color)
        # Lid bar
        d.rounded_rectangle([m, lid_y, s - m, lid_y + stroke],
                            radius=stroke // 2, fill=color)
        # Body outline
        d.rounded_rectangle([m + int(s * 0.06), body_top,
                             s - m - int(s * 0.06), s - m],
                            radius=stroke, outline=color, width=stroke)
        # Two slats
        slat_x = [s // 2 - int(s * 0.08), s // 2 + int(s * 0.08)]
        for sx in slat_x:
            d.rounded_rectangle([sx - stroke // 2,
                                 body_top + int(s * 0.10),
                                 sx + stroke // 2, s - m - int(s * 0.08)],
                                radius=stroke // 2, fill=color)

    else:
        # Unknown glyph: render a simple solid dot so something still appears
        # and the error is visually obvious.
        m = int(s * 0.30)
        d.ellipse([m, m, s - m, s - m], fill=color)

    return img.resize((size, size), Image.LANCZOS)


# ─── PhotoImage cache (per-Tk-root) ──────────────────────────────────────
# Tk PhotoImages must be kept alive by the Python side. We cache them by
# (kind, size, color...) so repeat calls don't re-render. Callers MUST keep
# the returned PhotoImage referenced for the lifetime of the widget that
# displays it — easiest pattern is `widget._photo = theme.get_glyph_photo(...)`.

_photo_cache: dict = {}


def get_glyph_photo(name: str, size: int, color: str):
    """Cached PhotoImage of a brand glyph. Requires a Tk root to exist."""
    from PIL import ImageTk
    key = ("glyph", name, size, color)
    if key not in _photo_cache:
        pil = render_glyph(name, size, color)
        _photo_cache[key] = ImageTk.PhotoImage(pil)
    return _photo_cache[key]


def get_mark_photo(size: int, *, border_color: str = CORAL,
                   glyph_color: str = CORAL, fill_color: str | None = None):
    """Cached PhotoImage of the Φ-in-circle brand mark."""
    from PIL import ImageTk
    key = ("mark", size, border_color, glyph_color, fill_color)
    if key not in _photo_cache:
        pil = render_mark_image(size, border_color=border_color,
                                glyph_color=glyph_color,
                                fill_color=fill_color)
        _photo_cache[key] = ImageTk.PhotoImage(pil)
    return _photo_cache[key]


def clear_photo_cache():
    """Drop all cached PhotoImages. Call only when a Tk root is being torn
    down and recreated; otherwise widgets pointing at cached PhotoImages will
    paint blanks."""
    _photo_cache.clear()


def ensure_brand_ico(out_path) -> "Path":
    """Generate (once) a multi-resolution .ico for window icons.
    Idempotent: if `out_path` already exists, returns immediately.

    The .ico embeds 16/32/48/64/128/256 px renders of the brand mark, so
    Windows can pick the right one for taskbar, alt-tab, file explorer, etc.
    """
    from pathlib import Path
    p = Path(out_path)
    if p.exists():
        return p
    sizes = [16, 32, 48, 64, 128, 256]
    imgs = [render_mark_image(s, border_color=CORAL,
                              glyph_color=CORAL, fill_color=INK)
            for s in sizes]
    # PIL's ICO writer takes the largest image and a `sizes` list of the
    # smaller resolutions to embed.
    imgs[-1].save(p, format="ICO",
                  sizes=[(s, s) for s in sizes])
    return p


# ─── Back-compat shim: draw_widget_mark (Canvas-based) ────────────────────
# Kept so older code that calls `theme.draw_widget_mark(canvas, size, ...)`
# still works. New code should use `get_mark_photo()` and display via a
# tk.Label or canvas.create_image — the PIL pipeline is dramatically crisper.

def draw_widget_mark(canvas, size: int, *, border_color: str = CORAL,
                     glyph_color: str = CORAL, fill_color: str = None):
    """Deprecated: paint the brand mark into a tk.Canvas using PIL rendering.
    Internally this now renders via PIL (anti-aliased) and pastes the result
    via canvas.create_image. The visual is identical to get_mark_photo()
    but you don't have to manage the PhotoImage reference yourself — we
    stash it on the canvas as `canvas._mark_photo`.
    """
    from PIL import ImageTk
    pil = render_mark_image(size, border_color=border_color,
                            glyph_color=glyph_color, fill_color=fill_color)
    photo = ImageTk.PhotoImage(pil)
    canvas._mark_photo = photo   # keep alive
    canvas.create_image(size // 2, size // 2, image=photo, anchor="center")
