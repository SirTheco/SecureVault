"""Custom canvas widgets in the lavender-clay style: buttons, chips, strength bar, secret entry."""
from __future__ import annotations

import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageDraw

from ..passwords import strength
from . import anim, gfx, theme
from .capslock import attach_caps_hint
from .gfx import S
from .theme import pick


def _lighten(hex_color: str, amount: float) -> str:
    c = gfx.hex_rgb(hex_color)
    return "#%02x%02x%02x" % tuple(int(v + (255 - v) * amount) for v in c)


def _darken(hex_color: str, amount: float) -> str:
    c = gfx.hex_rgb(hex_color)
    return "#%02x%02x%02x" % tuple(int(v * (1 - amount)) for v in c)


def copy_text(widget, text: str, secret: bool = False) -> None:
    """Copy to the clipboard. Secrets are wiped again after the configured delay."""
    root = widget.winfo_toplevel()
    handler = getattr(root, "copy_to_clipboard", None)
    if handler:
        handler(text, secret)
    else:
        widget.clipboard_clear()
        widget.clipboard_append(text)


# ---------------------------------------------------------------------- tooltip
class Tooltip:
    def __init__(self, widget, text: str):
        self.widget, self.text, self.tip, self._job = widget, text, None, None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._job = self.widget.after(450, self._show)

    def _cancel(self):
        if self._job:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    def _show(self):
        if self.tip or not self.widget.winfo_exists():
            return
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.attributes("-topmost", True)
        label = tk.Label(self.tip, text=self.text, bg="#1C1647", fg="#FFFFFF", padx=S(10), pady=S(4),
                         font=gfx.tkfont_for(11, "medium"), bd=0)
        label.pack()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2 - label.winfo_reqwidth() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + S(6)
        self.tip.wm_geometry(f"+{max(x, 0)}+{y}")

    def _hide(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None


# ----------------------------------------------------------------------- button
class GButton(tk.Canvas):
    """Gradient pill button drawn with Pillow (primary, teal, pink, orange, danger, soft, outline, ghost, white).

    Hover / press changes fade softly instead of snapping.
    """

    GRADS = {"primary": theme.PRIMARY_GRAD, "teal": theme.TEAL_GRAD, "pink": theme.PINK_GRAD,
             "orange": theme.ORANGE_GRAD, "blue": theme.BLUE_GRAD, "danger": ("#FF8A8E", "#E5484D")}

    def __init__(self, master, text: str = "", command=None, width: int | None = 180, height: int = 46,
                 style: str = "primary", icon: str | None = None, bg=None, size: int = 14, weight: str = "bold",
                 radius: int | None = None, tooltip: str | None = None, anchor: str = "center",
                 background_image: Image.Image | None = None, label_color: str | None = None):
        self.text, self.command, self.style, self.icon_name = text, command, style, icon
        self.background_image = background_image
        self.label_color = label_color
        self.size, self.weight, self.anchor_mode = size, weight, anchor
        self.h_log, self.radius_log = height, radius
        self.bg_pair = bg if bg is not None else theme.CARD
        label_w = gfx.pil_font(S(size), "bold" if weight == "bold" else "medium").getlength(text) / gfx.scale() if text else 0
        self.w_log = width if width else int(label_w + 44 + (26 if icon else 0))
        super().__init__(master, width=S(self.w_log), height=S(height), bg=pick(self.bg_pair),
                         highlightthickness=0, bd=0, cursor="hand2")
        self._state, self._pressed, self._hover = "normal", False, False
        self._item = self.create_image(0, 0, anchor="nw")
        self._fader = anim.Fader(self, self._item, self._render)
        self._fader.set("normal")
        self.bind("<Enter>", lambda _e=None: self._set_hover(True))
        self.bind("<Leave>", lambda _e=None: self._set_hover(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._release)
        if tooltip:
            Tooltip(self, tooltip)

    # ------------------------------------------------------------- rendering
    def _colors(self, variant: str):
        c1, c2 = (pick(c) if isinstance(c, tuple) else c for c in self.GRADS[self.style])
        if variant == "hover":
            c1, c2 = _lighten(c1, 0.12), _lighten(c2, 0.08)
        elif variant == "press":
            c1, c2 = _darken(c1, 0.08), _darken(c2, 0.12)
        return c1, c2

    def _render(self, variant: str) -> Image.Image:
        w, h = S(self.w_log), S(self.h_log)
        radius = S(self.radius_log) if self.radius_log else h // 2
        style = self.style
        text_color = "#FFFFFF"
        if style in self.GRADS:
            c1, c2 = self._colors(variant)
            img = gfx.gradient_pill(w, h, c1, c2, radius)
        elif style == "soft":
            fill, border, text_color = pick(theme.CARD_SOFT), pick(theme.BORDER), pick(theme.TEXT)
            if variant != "normal":
                fill = pick(theme.SELECTED)
            if variant == "press":
                fill = _darken(fill, 0.08)
            img = gfx.card_image(w, h, fill, radius, border)
        elif style == "white":
            text_color = pick(theme.PRIMARY)
            fill = "#E4DBFA" if variant == "press" else "#F1ECFF" if variant == "hover" else "#FFFFFF"
            img = gfx.card_image(w, h, fill, radius, None)
        elif style == "outline":
            text_color = pick(theme.PRIMARY)
            fill = pick(theme.SELECTED) if variant != "normal" else pick(self.bg_pair)
            if variant == "press":
                fill = _darken(fill, 0.08)
            img = gfx.card_image(w, h, fill, radius, pick(theme.PRIMARY))
        else:  # ghost
            text_color = pick(theme.MUTED if variant == "normal" else theme.TEXT)
            fill = pick(theme.HOVER) if variant != "normal" else pick(self.bg_pair)
            if variant == "press":
                fill = _darken(fill, 0.08)
            img = gfx.card_image(w, h, fill, radius, None)
        if self._state == "disabled":
            img = Image.blend(img, Image.new("RGBA", img.size, hex_to_rgba(pick(self.bg_pair))), 0.55)
            text_color = pick(theme.MUTED)
        img = img.copy()
        label_color = self.label_color if self.label_color and self._state != "disabled" else text_color
        label = gfx.text_image(self.text, self.size, label_color, "bold" if self.weight == "bold" else "medium") if self.text else None
        icon_img = gfx.icon(self.icon_name, 18, text_color) if self.icon_name else None
        gap = S(8)
        total = (label.width if label else 0) + (icon_img.width + (gap if label else 0) if icon_img else 0)
        x = (w - total) // 2 if self.anchor_mode == "center" else S(18)
        if icon_img:
            img.alpha_composite(icon_img, (x, (h - icon_img.height) // 2))
            x += icon_img.width + gap
        if label:
            img.alpha_composite(label, (x, (h - label.height) // 2 - S(1)))
        if self.background_image is not None:
            backdrop = self.background_image.convert("RGBA")
            if backdrop.size != img.size:
                backdrop = backdrop.resize(img.size, Image.Resampling.LANCZOS)
            backdrop.alpha_composite(img)
            img = backdrop
        return img

    # -------------------------------------------------------------- behaviour
    def _refresh(self, ms: float = 160):
        variant = "press" if self._pressed else "hover" if self._hover else "normal"
        self._fader.go(variant, 70 if variant == "press" else ms)

    def _set_hover(self, value: bool):
        self._hover = value and self._state != "disabled"
        self._pressed = self._pressed and self._hover
        self._refresh(150 if value else 240)

    def _press(self, _e):
        if self._state == "disabled":
            return
        self._pressed = True
        self._refresh()

    def _release(self, e):
        was = self._pressed
        self._pressed = False
        self._refresh(140)
        inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
        if was and inside and self.command:
            self.command()

    def set_text(self, text: str) -> None:
        self.text = text
        self._fader.invalidate()
        self._fader.set("hover" if self._hover else "normal")

    def set_state(self, state: str) -> None:
        self._state = state
        self._pressed = False
        self._fader.invalidate()
        self.configure(cursor="hand2" if state == "normal" else "arrow")
        self._fader.set("normal")

    def destroy(self):
        self._fader.destroy()
        super().destroy()


def hex_to_rgba(h: str):
    return gfx.hex_rgb(h) + (255,)


# ------------------------------------------------------------------ icon button
class IconButton(tk.Canvas):
    def __init__(self, master, icon: str, command=None, size: int = 36, icon_size: int = 18, bg=None,
                 color=None, hover_color=None, tooltip: str | None = None, active: bool = False,
                 hover_bg=None):
        self.bg_pair = bg if bg is not None else theme.CARD
        self.icon_name, self.command, self.size_log, self.icon_size = icon, command, size, icon_size
        self.color_pair = color or theme.MUTED
        self.hover_color_pair = hover_color or theme.PRIMARY
        self.hover_bg_pair = hover_bg or theme.HOVER
        self.active = active
        super().__init__(master, width=S(size), height=S(size), bg=pick(self.bg_pair), highlightthickness=0, bd=0,
                         cursor="hand2")
        self._hover = False
        self._pressed = False
        self._item = self.create_image(0, 0, anchor="nw")
        self._fader = anim.Fader(self, self._item, self._render)
        self._fader.set("rest")
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._click)
        if tooltip:
            Tooltip(self, tooltip)

    def _render(self, state: str) -> Image.Image:
        s = S(self.size_log)
        hovered = state in ("hover", "press")
        # A soft centered halo and subtle icon-size change crossfade on hover.
        # The icon never shakes or drifts around the screen.
        img = gfx.card_image(s, s, pick(self.hover_bg_pair), s // 2, None) if hovered else Image.new("RGBA", (s, s), (0, 0, 0, 0))
        if state == "press":
            img = gfx.card_image(s, s, pick(theme.SELECTED), s // 2, None)
        if not hovered:
            # keep RGB equal to the hover disc so the cross-fade has no dark fringe
            img = Image.new("RGBA", (s, s), gfx.hex_rgb(pick(self.hover_bg_pair)) + (0,))
        col = pick(self.hover_color_pair if (hovered or self.active) else self.color_pair)
        icon_size = min(self.size_log - 8, self.icon_size + (1 if state == "hover" else 0))
        ic = gfx.icon(self.icon_name, max(1, icon_size), col)
        img.alpha_composite(ic, ((s - ic.width) // 2, (s - ic.height) // 2))
        return img

    def _set(self, value: bool):
        self._hover = value
        if not value:
            self._pressed = False
        self._fader.go("press" if self._pressed else "hover" if value else "rest", 140 if value else 220)

    def _press(self, _e):
        self._pressed = True
        self._fader.go("press", 80)

    def _click(self, e):
        was = self._pressed
        self._pressed = False
        self._fader.go("hover" if self._hover else "rest", 180)
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.command()

    def set_icon(self, name: str, active: bool | None = None) -> None:
        self.icon_name = name
        if active is not None:
            self.active = active
        self._fader.invalidate()
        self._fader.set("hover" if self._hover else "rest")

    def destroy(self):
        self._fader.destroy()
        super().destroy()


# --------------------------------------------------------------------------- chip
class Chip(tk.Canvas):
    def __init__(self, master, text: str, command=None, selected: bool = False, grad=theme.PRIMARY_GRAD,
                 bg=None, height: int = 32, size: int = 12):
        self.text, self.command, self.selected, self.grad = text, command, selected, grad
        self.bg_pair = bg if bg is not None else theme.CARD
        self.size_log, self.h_log = size, height
        label_w = gfx.pil_font(S(size), "medium").getlength(text) / gfx.scale()
        self.w_log = int(label_w + 30)
        super().__init__(master, width=S(self.w_log), height=S(height), bg=pick(self.bg_pair), highlightthickness=0,
                         bd=0, cursor="hand2")
        self._hover = False
        self._pressed = False
        self._item = self.create_image(0, 0, anchor="nw")
        self._fader = anim.Fader(self, self._item, self._render)
        self._fader.set(self._state_name())
        self.bind("<Enter>", lambda _e=None: self._set(True))
        self.bind("<Leave>", lambda _e=None: self._set(False))
        self.bind("<ButtonPress-1>", self._press)
        self.bind("<ButtonRelease-1>", self._click)

    def _state_name(self) -> str:
        if self._pressed:
            return "press_on" if self.selected else "press"
        return "on" if self.selected else "hover" if self._hover else "off"

    def _render(self, state: str) -> Image.Image:
        w, h = S(self.w_log), S(self.h_log)
        if state in ("on", "press_on"):
            c1, c2 = (pick(c) for c in self.grad)
            if state == "press_on":
                c1, c2 = _darken(c1, 0.12), _darken(c2, 0.12)
            img = gfx.gradient_pill(w, h, c1, c2)
            color = "#FFFFFF"
        else:
            fill = pick(theme.SELECTED if state in ("hover", "press") else theme.CARD_SOFT)
            if state == "press":
                fill = _darken(fill, 0.08)
            img = gfx.card_image(w, h, fill, h // 2, pick(theme.BORDER))
            color = pick(theme.TEXT)
        label = gfx.text_image(self.text, self.size_log, color, "medium")
        img = img.copy()
        img.alpha_composite(label, ((w - label.width) // 2, (h - label.height) // 2 - S(1)))
        return img

    def _set(self, value):
        self._hover = value
        if not value:
            self._pressed = False
        self._fader.go(self._state_name(), 140)

    def _press(self, _e):
        self._pressed = True
        self._fader.go(self._state_name(), 80)

    def set_selected(self, value: bool):
        self.selected = value
        self._fader.go(self._state_name(), 240)

    def _click(self, e):
        was = self._pressed
        self._pressed = False
        self._fader.go(self._state_name(), 180)
        if was and 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height() and self.command:
            self.command()

    def destroy(self):
        self._fader.destroy()
        super().destroy()


# ------------------------------------------------------------------ strength bar
class StrengthMeter(tk.Canvas):
    """Five soft segments + a label. The bar fills smoothly when the password changes."""

    def __init__(self, master, bg=None, width: int = 320):
        self.bg_pair = bg if bg is not None else theme.CARD
        self.w_log = width
        super().__init__(master, width=S(width), height=S(22), bg=pick(self.bg_pair), highlightthickness=0, bd=0)
        self._ph = None
        self._item = self.create_image(0, 0, anchor="nw")
        self._level = -1.0          # displayed level (animated)
        self._target = -1
        self._label = ""
        self._color = "#000000"
        self._draw()

    def update_for(self, password: str) -> None:
        level, label, bits = (strength(password) if password else (-1, "", 0))
        self._label = f"{label}  ~{int(bits)} bits" if password else ""
        self._target = level
        if level >= 0:
            self._color = theme.STRENGTH[level]
        start_level = self._level
        anim.start(("meter", id(self)), 260, lambda t: self._set_level(start_level + (level - start_level) * t),
                   ease=anim.ease_out)

    def _set_level(self, value: float) -> None:
        self._level = value
        self._draw()

    def _draw(self) -> None:
        w, h = S(self.w_log), S(22)
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        seg_w = int(w * 0.52 / 5)
        gap = S(4)
        track = gfx.hex_rgb(pick(theme.BORDER)) + (255,)
        fill = gfx.hex_rgb(self._color) + (255,)
        for i in range(5):
            x0 = i * (seg_w + gap)
            box = (x0, h // 2 - S(3), x0 + seg_w, h // 2 + S(3))
            d.rounded_rectangle(box, radius=S(3), fill=track)
            part = max(0.0, min(1.0, self._level + 1 - i))      # 0..1 how much of this segment is filled
            if part > 0:
                x1 = x0 + max(S(6), int(seg_w * part))
                d.rounded_rectangle((x0, box[1], x1, box[3]), radius=S(3), fill=fill)
        if self._label:
            txt = gfx.text_image(self._label, 11, self._color, "medium")
            img.alpha_composite(txt, (5 * seg_w + 4 * gap + S(12), (h - txt.height) // 2 - S(1)))
        old = self._ph
        self._ph = gfx.photo(img)
        self.itemconfigure(self._item, image=self._ph)
        if old is not None:
            gfx.release(old)


# --------------------------------------------------------------------- inputs
def entry(master, placeholder: str = "", show: str = "", height: int = 42, width: int | None = None,
          bg=None, **kw) -> ctk.CTkEntry:
    opts = dict(height=height, corner_radius=14, border_width=1, fg_color=theme.INPUT, border_color=theme.BORDER,
                text_color=theme.TEXT, placeholder_text_color=theme.MUTED, placeholder_text=placeholder,
                font=theme.font(13), show=show)
    if width:
        opts["width"] = width
    if bg is not None:
        opts["bg_color"] = bg
    opts.update(kw)
    return ctk.CTkEntry(master, **opts)


class SecretEntry(ctk.CTkFrame):
    """Masked entry with eye / copy / generate icon buttons."""

    def __init__(self, master, on_change=None, on_generate=None, bg=None, placeholder: str = "", reveal: bool = False,
                 copy: bool = True):
        super().__init__(master, fg_color="transparent")
        self.bg_pair = bg if bg is not None else theme.CARD
        self.columnconfigure(0, weight=1)
        self.entry = entry(self, placeholder, show="" if reveal else "•")
        self.entry.grid(row=0, column=0, sticky="ew")
        self._hidden = not reveal
        col = 1
        self.eye = IconButton(self, "eye" if self._hidden else "eye_off", self.toggle, bg=self.bg_pair, tooltip="Show / hide")
        self.eye.grid(row=0, column=col, padx=(6, 0))
        col += 1
        if copy:
            IconButton(self, "copy", lambda: copy_text(self, self.get(), True), bg=self.bg_pair, tooltip="Copy").grid(
                row=0, column=col, padx=(2, 0))
            col += 1
        if on_generate:
            IconButton(self, "dice", on_generate, bg=self.bg_pair, tooltip="Generate password").grid(
                row=0, column=col, padx=(2, 0))
        if on_change:
            self.entry.bind("<KeyRelease>", lambda _e=None: on_change())
        attach_caps_hint(self.entry, self, row=1, column=0, pady=(2, 0))

    def toggle(self) -> None:
        self._hidden = not self._hidden
        self.entry.configure(show="•" if self._hidden else "")
        self.eye.set_icon("eye" if self._hidden else "eye_off")

    def get(self) -> str:
        return self.entry.get()

    def set(self, value: str) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, value)
