"""splash.py - the cait-whisper startup splash.

A borderless, screen-centered card shown while the speech model loads. The
brand mark (Phi-in-circle) is the fixed backdrop; six coral particles drift
and bounce inside the ring so the mark reads as "coming alive" while the app
warms up. An indeterminate coral shimmer bar keeps the wait feeling active no
matter how long the first-run model download takes.

This matters most on the very first launch, when the model is downloaded
(~a minute): without a splash, a non-technical user has no signal that
anything is happening. With it, the wait is a calm, on-brand brand moment.

Pure Tkinter + PIL (no CustomTkinter) so it adds no new dependency to the
bundle. Design and lifecycle mirror Cait Meeting Scribe's splash:

    sp = SplashScreen(root)        # root is the (already-created) Tk root
    sp.set_status("Preparing...")  # optional status text
    sp.finish()                    # cancels animation + destroys (idempotent)

The owner (client.main) guarantees finish() runs - on model ready, on error,
or via a safety timeout - so the splash can never trap the user.
"""

from __future__ import annotations

import math
import random
import tkinter as tk

import theme


class SplashScreen(tk.Toplevel):
    W = 300
    H = 350
    MARK_PX = 150          # rendered size of the Phi-in-circle backdrop
    N_DOTS = 7             # seven stars - Vogel phyllotaxis n=0..6 per brand spec
    DOT_R = 3.5
    TICK_MS = 22           # ~45 fps
    SPEED_MIN = 0.6
    SPEED_MAX = 1.7
    SPEED_CAP = 3.0
    WAVE_W = 214           # loading waveform (the app's coral wave, not a bar)
    WAVE_H = 28
    N_WAVE = 15

    def __init__(self, parent):
        super().__init__(parent)
        self.overrideredirect(True)
        self.configure(bg=theme.INK)
        try:
            self.attributes("-topmost", True)
        except Exception:
            pass

        self._anim_job = None
        self._dots: list[dict] = []
        self._mark_photo = None
        self._wave_phase = 0.0

        self._place_center()
        self._build()
        self._init_particles()
        try:
            self.lift()
        except Exception:
            pass
        self._animate()

    # ── placement ─────────────────────────────────────────────────────────

    def _place_center(self):
        """Center on the primary screen using our FIXED size (no winfo race)."""
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = max(0, (sw - self.W) // 2)
        y = max(0, (sh - self.H) // 2)
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")

    # ── construction ──────────────────────────────────────────────────────

    def _build(self):
        # 1px INK_MUTE border (same convention as the hover card).
        border = tk.Frame(self, bg=theme.INK_MUTE)
        border.pack(fill="both", expand=True)
        inner = tk.Frame(border, bg=theme.INK)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        self._canvas = tk.Canvas(
            inner, width=self.MARK_PX, height=self.MARK_PX,
            bg=theme.INK, highlightthickness=0, bd=0,
        )
        self._canvas.pack(pady=(28, 10))

        # Static backdrop: the Phi-in-circle mark (coral ring + Phi on INK).
        try:
            self._mark_photo = theme.get_mark_photo(
                self.MARK_PX, border_color=theme.CORAL,
                glyph_color=theme.CORAL, fill_color=theme.INK,
            )
            self._canvas.create_image(
                self.MARK_PX / 2, self.MARK_PX / 2, image=self._mark_photo,
            )
        except Exception:
            pass

        # "Cait. whisper" lockup as the hero wordmark.
        try:
            theme.brand_lockup(
                inner, bg=theme.INK, fg=theme.PAPER,
                cait_size=20, period_size=23, whisper_size=18,
            ).pack(pady=(2, 2))
        except Exception:
            tk.Label(inner, text="Cait. whisper", bg=theme.INK,
                     fg=theme.PAPER, font=theme.t_title()).pack(pady=(2, 2))

        self._status = tk.Label(
            inner, text="Starting...", bg=theme.INK, fg=theme.INK_FAINT,
            font=theme.t_caption(),
        )
        self._status.pack(pady=(4, 10))

        # Loading waveform - the same coral wave language the app uses while
        # recording/processing, instead of a generic progress bar. Animated
        # with the app's organic multi-wave flow so it never visibly loops.
        self._wave = tk.Canvas(
            inner, width=self.WAVE_W, height=self.WAVE_H,
            bg=theme.INK, highlightthickness=0, bd=0,
        )
        self._wave.pack(pady=(0, 20))
        # A FILLED coral wave (the app's default waveform style) as the
        # loading bar - one smooth polygon, animated below.
        self._wave_poly = self._wave.create_polygon(
            0, 0, 0, 0, 0, 0, fill=theme.CORAL, outline="",
            smooth=True, splinesteps=24,
        )

    # ── particle simulation (bounce inside the ring) ──────────────────────

    def _init_particles(self):
        self._cx = self._cy = self.MARK_PX / 2.0
        # Keep particles inside the coral ring: ring sits at a ~12% inset with
        # a stroke of ~size/14. Stay inside that, minus the particle radius.
        inset = self.MARK_PX * 0.12
        stroke = self.MARK_PX / 14.0
        self._R = max(8.0, self.MARK_PX / 2.0 - inset - stroke - self.DOT_R)

        GOLDEN_ANGLE = 137.5
        for n in range(1, self.N_DOTS + 1):
            rad = self._R * (0.35 + 0.5 * (n / self.N_DOTS))
            ang = math.radians(n * GOLDEN_ANGLE)
            x = self._cx + rad * math.cos(ang)
            y = self._cy + rad * math.sin(ang)
            speed = random.uniform(self.SPEED_MIN, self.SPEED_MAX)
            vang = random.uniform(0.0, 2 * math.pi)
            # Central star (n=1, first after center) = deeper coral per spec:
            # "Φ is deeper coral (#ed6f5c) than surrounding stars at all layers"
            # n=0 is the innermost/central position in Vogel layout.
            star_color = theme.CORAL if n == 1 else theme.CORAL_SOFT
            self._dots.append({
                "x": x, "y": y,
                "vx": speed * math.cos(vang),
                "vy": speed * math.sin(vang),
                "r": self.DOT_R,
                "id": self._canvas.create_oval(0, 0, 0, 0,
                                               fill=star_color, outline=""),
            })
        self._draw_dots()

    def _step(self):
        cx, cy, R = self._cx, self._cy, self._R
        for d in self._dots:
            d["x"] += d["vx"]
            d["y"] += d["vy"]
            dx, dy = d["x"] - cx, d["y"] - cy
            dist = math.hypot(dx, dy)
            if dist > R and dist > 0:                 # bounce off the ring
                nx, ny = dx / dist, dy / dist
                vdotn = d["vx"] * nx + d["vy"] * ny
                d["vx"] -= 2 * vdotn * nx
                d["vy"] -= 2 * vdotn * ny
                over = dist - R
                d["x"] -= nx * over
                d["y"] -= ny * over

        n = len(self._dots)
        for i in range(n):                            # pairwise elastic bounce
            a = self._dots[i]
            for j in range(i + 1, n):
                b = self._dots[j]
                dx, dy = b["x"] - a["x"], b["y"] - a["y"]
                dd = math.hypot(dx, dy)
                mind = a["r"] + b["r"]
                if 0 < dd < mind:
                    nx, ny = dx / dd, dy / dd
                    p = (a["vx"] - b["vx"]) * nx + (a["vy"] - b["vy"]) * ny
                    if p > 0:
                        a["vx"] -= p * nx; a["vy"] -= p * ny
                        b["vx"] += p * nx; b["vy"] += p * ny
                    over = (mind - dd) / 2
                    a["x"] -= nx * over; a["y"] -= ny * over
                    b["x"] += nx * over; b["y"] += ny * over

        cap = self.SPEED_CAP
        for d in self._dots:                          # clamp runaway speed
            sp = math.hypot(d["vx"], d["vy"])
            if sp > cap:
                d["vx"] *= cap / sp
                d["vy"] *= cap / sp

    def _draw_dots(self):
        for d in self._dots:
            r = d["r"]
            try:
                self._canvas.coords(
                    d["id"], d["x"] - r, d["y"] - r, d["x"] + r, d["y"] + r,
                )
            except Exception:
                return

    def _draw_wave(self):
        """Animate a FILLED coral wave (the app's default waveform style) with
        the organic multi-wave flow - a sum of incommensurate sines, center-
        symmetric - so the splash loading bar speaks the same wave language the
        app uses while recording, and never visibly repeats."""
        n = self.N_WAVE
        cw, ch = self.WAVE_W, self.WAVE_H
        cy = ch / 2.0
        max_amp = (ch - 4) / 2.0
        center = (n - 1) / 2.0
        p = self._wave_phase
        top, bot = [], []
        for i in range(n):
            d = abs(i - center) / center
            w = (math.sin(p - d * 2.2)
                 + 0.6 * math.sin(p * 0.61 - d * 3.7)
                 + 0.4 * math.sin(p * 1.70 + d * 1.3))
            norm = min(1.0, max(0.0, (w / 2.0) * 0.5 + 0.5))
            amp = max(1.0, (0.12 + 0.72 * norm) * max_amp)
            x = 3 + (i / (n - 1)) * (cw - 6)
            top.append((x, cy - amp))
            bot.append((x, cy + amp))
        pts = [c for xy in top for c in xy] + [c for xy in reversed(bot) for c in xy]
        try:
            self._wave.coords(self._wave_poly, *pts)
        except Exception:
            return

    def _animate(self):
        self._step()
        self._draw_dots()
        self._wave_phase += 0.30
        self._draw_wave()
        self._anim_job = self.after(self.TICK_MS, self._animate)

    # ── public API ────────────────────────────────────────────────────────

    def set_status(self, text: str):
        try:
            self._status.configure(text=text)
            self.update_idletasks()
        except Exception:
            pass

    def finish(self):
        """Stop the animation and close the splash. Idempotent."""
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except Exception:
                pass
            self._anim_job = None
        try:
            self.destroy()
        except Exception:
            pass
