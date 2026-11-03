"""Purple gradient navigation rail on one canvas, with a sliding selection pill and soft hover glow."""
from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw

from . import anim, gfx, theme
from .gfx import S
from .theme import pick

WIDTH = 224
_panel_cache: dict = {}


class Sidebar(tk.Canvas):
    NAV = (("all", "grid", "All items"), ("favorites", "star", "Favorites"), ("attention", "shield_alert", "Security check"))

    def __init__(self, master, on_nav, on_settings, on_lock, counts=None):
        super().__init__(master, width=S(WIDTH), bg=pick(theme.PAGE), highlightthickness=0, bd=0)
        self.on_nav, self.on_settings, self.on_lock = on_nav, on_settings, on_lock
        self.counts = counts or {}
        self.active = "all"
        self.hover: str | None = None
        self.lock_text = ""
        self._photos: list = []
        self._size = (0, 0)
        self._fonts: dict = {}
        self._zones: list[tuple[str, int, int, int, int]] = []
        self._rows: dict[str, int] = {}              # key -> top y of its row
        self._pill_y: float | None = None
        self._hover_y: float = 0.0
        self._hover_alpha = 0.0
        self._lock_alpha = 0.0
        self._pill_cache: dict = {}
        self._ids: dict[str, int] = {}
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e=None: self._set_hover(None))
        self.bind("<Button-1>", self._click)

    # -------------------------------------------------------------- public
    def set_active(self, key: str) -> None:
        if key == self.active:
            return
        self.active = key
        self._slide_pill()

    def set_counts(self, counts: dict) -> None:
        if counts != self.counts:
            self.counts = counts
            self.redraw()

    def set_lock_text(self, text: str) -> None:
        if text != self.lock_text:
            self.lock_text = text
            if "lock_sub" in self._ids:
                self.itemconfigure(self._ids["lock_sub"], text=text or "Auto-lock on")

    # ------------------------------------------------------------- drawing
    def _on_configure(self, event):
        if (event.width, event.height) != self._size:
            self._size = (event.width, event.height)
            self.redraw()

    def _font(self, size, weight="normal"):
        key = (size, weight)
        if key not in self._fonts:
            self._fonts[key] = gfx.tkfont_for(size, weight)
        return self._fonts[key]

    def _keep(self, img):
        ph = gfx.photo(img)
        self._photos.append(ph)
        return ph

    def _pill_photo(self, w: int, h: int, alpha: float, radius: int):
        a = round(max(0.0, min(1.0, alpha)) * 12) / 12
        key = (w, h, a)
        if key not in self._pill_cache:
            fill = Image.new("RGBA", (w, h), (255, 255, 255, int(255 * a)))
            fill.putalpha(gfx.rounded_mask((w, h), radius).point(lambda v: int(v * a)))
            self._pill_cache[key] = self._keep(fill)
        return self._pill_cache[key]

    def _row_y(self, key: str) -> int:
        return self._rows.get(key, 0)

    def redraw(self):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 50:
            return
        for k in ("pill", "hover"):
            anim.cancel(("sidebar", id(self), k))
        for ph in self._photos:
            gfx.release(ph)
        self._photos.clear()
        self._pill_cache.clear()
        self._zones.clear()
        self._ids.clear()
        self.delete("all")
        key = (w, h, theme.dark(), pick(theme.SIDEBAR_TOP), pick(theme.SIDEBAR_BOTTOM))
        if key not in _panel_cache:
            _panel_cache.clear()
            _panel_cache[key] = gfx.panel_image(w, h, pick(theme.SIDEBAR_TOP), pick(theme.SIDEBAR_BOTTOM), S(34), angle=75)
        self.create_image(0, 0, anchor="nw", image=self._keep(_panel_cache[key]))
        for fx, fy, r in ((0.84, 0.07, 3), (0.70, 0.55, 2), (0.18, 0.62, 2)):
            self.create_oval(w * fx - S(r), h * fy - S(r), w * fx + S(r), h * fy + S(r), fill="#D9CCFF", outline="")
        x0, row_h = S(14), S(48)
        pill_w = w - 2 * x0
        # row positions
        self._rows = {}
        y = S(112)
        for k, _i, _l in self.NAV:
            self._rows[k] = y
            y += S(54)
        self._rows["settings"] = h - S(168)
        self._pill_y = float(self._rows.get(self.active, S(112)))
        self._hover_y = float(self._rows.get(self.hover or self.active, S(112)))
        # sliding pills (below the labels)
        self._ids["pill"] = self.create_image(x0, self._pill_y, anchor="nw", image=self._pill_photo(pill_w, row_h, 0.26, S(16)))
        self._ids["hover"] = self.create_image(x0, self._hover_y, anchor="nw", image=self._pill_photo(pill_w, row_h, self._hover_alpha * 0.12, S(16)))
        self._ids["lockglow"] = self.create_image(x0, h - S(98), anchor="nw", image=self._pill_photo(pill_w, S(76), 0.0, S(26)))
        # brand
        self.create_image(S(26), S(40), anchor="w", image=self._keep(gfx.sprite("app_icon", width=40)))
        self.create_text(S(78), S(40), anchor="w", text="SecureVault", fill="#FFFFFF", font=self._font(17, "bold"))
        self.create_text(S(30), S(92), anchor="w", text="MENU", fill="#D9CCFF", font=self._font(10, "bold"))
        for k, icon, label in self.NAV:
            self._nav_content(k, icon, label, self._rows[k], w, x0, row_h)
        self._nav_content("settings", "gear", "Settings", self._rows["settings"], w, x0, row_h)
        by = h - S(98)
        card = Image.new("RGBA", (w - S(28), S(76)), (0, 0, 0, 0))
        base = Image.new("RGBA", card.size, (255, 255, 255, 46))
        base.putalpha(gfx.rounded_mask(card.size, S(26)).point(lambda v: int(v * 46 / 255)))
        self.create_image(S(14), by, anchor="nw", image=self._keep(base))
        self.create_image(S(14) + S(40), by + S(38), anchor="center", image=self._keep(self._lock_button()))
        self.create_text(S(14) + S(80), by + S(28), anchor="w", text="Lock now", fill="#FFFFFF", font=self._font(13, "bold"))
        self._ids["lock_sub"] = self.create_text(S(14) + S(80), by + S(50), anchor="w", text=self.lock_text or "Auto-lock on",
                                                 fill="#E4DAFF", font=self._font(10))
        self._zones.append(("lock", S(14), by, w - S(14), by + S(76)))

    def _nav_content(self, key, icon, label, y, w, x0, h):
        self.create_image(x0 + S(18), y + h // 2, anchor="w", image=self._keep(gfx.icon(icon, 20, "#FFFFFF")))
        self.create_text(x0 + S(52), y + h // 2, anchor="w", text=label, fill="#FFFFFF",
                         font=self._font(13, "medium"))
        count = self.counts.get(key)
        if count:
            attention = key == "attention"
            bw = S(28) if count < 100 else S(36)
            bimg = Image.new("RGBA", (bw, S(22)), (0, 0, 0, 0))
            fill = gfx.hex_rgb("#FF7A8A" if attention else "#FFFFFF") + ((255,) if attention else (70,))
            ImageDraw.Draw(bimg).rounded_rectangle((0, 0, bw - 1, S(22) - 1), radius=S(11), fill=fill)
            self.create_image(w - x0 - S(14), y + h // 2, anchor="e", image=self._keep(bimg))
            self.create_text(w - x0 - S(14) - bw // 2, y + h // 2, text=str(count), fill="#FFFFFF", font=self._font(11, "bold"))
        self._zones.append((key, x0, y, w - x0, y + h))

    def _lock_button(self):
        size = S(52)
        pad = S(8)
        img = Image.new("RGBA", (size + pad * 2, size + pad * 2), (0, 0, 0, 0))
        glow = gfx.soft_blob((size, size), "#2A1580", 0.45, S(6))
        img.alpha_composite(glow, (pad - glow.width // 2 + size // 2, pad - glow.height // 2 + size // 2 + S(4)))
        disc = gfx.gradient_pill(size, size, "#FFFFFF", "#E4DAFF", size // 2)
        img.alpha_composite(disc, (pad, pad))
        ic = gfx.icon("lock", 24, pick(theme.PRIMARY))
        img.alpha_composite(ic, (pad + (size - ic.width) // 2, pad + (size - ic.height) // 2))
        return img

    # --------------------------------------------------------- animations
    def _slide_pill(self) -> None:
        if "pill" not in self._ids or self._pill_y is None:
            self.redraw()
            return
        target = float(self._rows.get(self.active, self._pill_y))
        begin = self._pill_y

        def step(t: float) -> None:
            self._pill_y = begin + (target - begin) * t
            self.coords(self._ids["pill"], S(14), self._pill_y)
        anim.start(("sidebar", id(self), "pill"), 340, step, ease=anim.ease_out)


    def _glow(self, key: str | None) -> None:
        """Move/fade the hover glow towards the hovered row (rows only) and fade the lock card glow."""
        if "hover" not in self._ids:
            return
        w = self.winfo_width()
        pill_w = w - 2 * S(14)
        row_key = key if key in self._rows else None
        target_a = 1.0 if row_key else 0.0
        if row_key:
            target_y = float(self._rows[row_key])
            if self._hover_alpha < 0.05:
                self._hover_y = target_y                      # appear in place, glide when moving between rows
            begin_y = self._hover_y
        else:
            target_y, begin_y = self._hover_y, self._hover_y
        begin_a = self._hover_alpha
        lock_target = 1.0 if key == "lock" else 0.0
        lock_begin = self._lock_alpha

        def step(t: float) -> None:
            self._hover_y = begin_y + (target_y - begin_y) * t
            self._hover_alpha = begin_a + (target_a - begin_a) * t
            self.coords(self._ids["hover"], S(14), self._hover_y)
            self.itemconfigure(self._ids["hover"], image=self._pill_photo(pill_w, S(48), self._hover_alpha * 0.12, S(16)))
            self._lock_alpha = lock_begin + (lock_target - lock_begin) * t
            self.itemconfigure(self._ids["lockglow"], image=self._pill_photo(pill_w, S(76), self._lock_alpha * 0.10, S(26)))
        anim.start(("sidebar", id(self), "hover"), 170, step, ease=anim.ease_out)

    # ------------------------------------------------------------ interaction
    def _hit(self, x, y):
        for key, x0, y0, x1, y1 in self._zones:
            if x0 <= x <= x1 and y0 <= y <= y1:
                return key
        return None

    def _motion(self, e):
        self._set_hover(self._hit(e.x, e.y))

    def _set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.configure(cursor="hand2" if key else "arrow")
            self._glow(key)

    def _click(self, e):
        key = self._hit(e.x, e.y)
        if key == "settings":
            self.on_settings()
        elif key == "lock":
            self.on_lock()
        elif key:
            self.on_nav(key)

    def destroy(self):
        for k in ("pill", "hover"):
            anim.cancel(("sidebar", id(self), k))
        for ph in self._photos:
            gfx.release(ph)
        super().destroy()
