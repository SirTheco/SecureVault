"""The account cards shown in the list column (soft hover, selection and entrance animations)."""
from __future__ import annotations

import tkinter as tk
import re

from PIL import Image

from . import anim, gfx, theme
from .gfx import S
from .theme import pick

ROW_H = 74


def ellipsize(font, text: str, max_px: int) -> str:
    if font.measure(text) <= max_px:
        return text
    while text and font.measure(text + "…") > max_px:
        text = text[:-1]
    return text + "…"


class AccountRow(tk.Canvas):
    def __init__(self, master, item, subtitle: str, selected: bool, flags: list[str], on_open, on_star, on_copy,
                 reveal_delay: float | None = None):
        super().__init__(master, height=S(ROW_H), bg=pick(theme.CARD), highlightthickness=0, bd=0, cursor="hand2")
        self.item, self.subtitle, self.selected, self.flags = item, subtitle, selected, flags
        color = item.data.get("title_color", "")
        self.title_color = color if isinstance(color, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", color) else None
        self.on_open, self.on_star, self.on_copy = on_open, on_star, on_copy
        self.hover = False
        self._cw = 0
        self._hover_level = 0.0
        self._reveal = 1.0 if reveal_delay is None else 0.0
        self._reveal_delay = reveal_delay
        self._zones: dict[str, tuple[int, int, int, int]] = {}
        self._keep: list = []
        self._ids: dict[str, int] = {}
        self._fader: anim.Fader | None = None
        self._icon_cache: dict = {}
        self.f_title = gfx.tkfont_for(14, "bold")
        self.f_sub = gfx.tkfont_for(11)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Enter>", lambda _e=None: self._set_hover(True))
        self.bind("<Leave>", lambda _e=None: self._set_hover(False))
        self.bind("<ButtonRelease-1>", self._click)

    # ----------------------------------------------------------------- build
    def _on_configure(self, e) -> None:
        if e.width != self._cw:
            self._build(e.width)

    def _state(self) -> str:
        return "selected" if self.selected else "hover" if self.hover else "normal"

    def _render_bg(self, state: str) -> Image.Image:
        w, h = self._cw, S(ROW_H)
        if state == "selected":
            return gfx.card_image(w, h, pick(theme.SELECTED), S(22), pick(theme.PRIMARY))
        if state == "hover":
            return gfx.card_image(w, h, pick(theme.HOVER), S(22), pick(theme.BORDER))
        base = gfx.card_image(w, h, pick(theme.CARD_SOFT), S(22), None)
        return base

    def _build(self, w: int) -> None:
        if w < 40:
            return
        self._cw = w
        h = S(ROW_H)
        if self._fader:
            self._fader.destroy()
        for ph in self._keep:
            gfx.release(ph)
        self._keep.clear()
        self._icon_cache.clear()
        self.delete("all")
        self._zones.clear()
        self._ids.clear()
        bg = self.create_image(0, 0, anchor="nw")
        self._fader = anim.Fader(self, bg, self._render_bg)
        self._fader.set(self._state())
        av_img = gfx.avatar(self.item.title, 48, self.item.data.get("icon_color", ""))
        self._avatar_pil = av_img
        self._ids["avatar"] = self.create_image(S(14), h // 2, anchor="w")
        right = w - S(14)
        fav = bool(self.item.data.get("favorite"))
        self._fav = fav
        sx = right - S(10)
        self._ids["star"] = self.create_image(sx, h // 2, anchor="e")
        self._zones["star"] = (sx - S(26), 0, sx + S(4), h)
        right = sx - S(30)
        has_pw = bool(self.item.data.get("password"))
        self._has_copy = has_pw
        self._ids["copy"] = self.create_image(right, h // 2, anchor="e")
        self._zones["copy"] = (right - S(28), 0, right + S(6), h)
        right -= S(34) if has_pw else 0
        self._right_text = right
        text_x = S(14) + S(48) + S(14)
        self._text_x = text_x
        room = right - text_x - S(6)
        title = ellipsize(self.f_title, self.item.title, room)
        self._ids["title"] = self.create_text(text_x, h // 2 - S(11), anchor="w", text=title, fill=pick(theme.TEXT),
                                              font=self.f_title)
        self._ids["sub"] = self.create_text(
            text_x, h // 2 + S(12), anchor="w", text=ellipsize(self.f_sub, self.subtitle or "No username", room),
            fill=pick(theme.MUTED), font=self.f_sub)
        if self.flags:
            tw = self.f_title.measure(title)
            label, color = (("Weak", "#E5484D") if "weak" in self.flags else
                            ("Reused", "#F2A33A") if "reused" in self.flags else ("Old", "#7C77A6"))
            badge = gfx.text_image(label, 9, "#FFFFFF", "bold")
            pill = gfx.card_image(badge.width + S(12), S(16), color, S(8), None)
            pill.alpha_composite(badge, (S(6), (S(16) - badge.height) // 2 - S(1)))
            self._badge_pil = pill
            if text_x + tw + S(8) + pill.width < right:
                self._ids["badge"] = self.create_image(text_x + tw + S(8), h // 2 - S(11), anchor="w")
        self._apply_dynamic()
        if self._reveal < 1.0:                     # start invisible, a little to the right
            self.itemconfigure(bg, image=self._reveal_bg(0.0))
            self._dx = 0
            self._slide(S(16))
        if self._reveal_delay is not None and self._reveal < 1.0:
            delay, self._reveal_delay = self._reveal_delay, None
            anim.start(("row", id(self)), 340, self._set_reveal, ease=anim.ease_out, delay_ms=delay)

    # ------------------------------------------------------------- dynamics
    def _img(self, key: str, pil: Image.Image, alpha: float):
        a = round(max(0.0, min(1.0, alpha)) * 8) / 8
        ck = (key, a)
        if ck not in self._icon_cache:
            ph = gfx.photo(anim.with_alpha(pil, a))
            self._keep.append(ph)
            self._icon_cache[ck] = ph
        return self._icon_cache[ck]

    def _apply_dynamic(self) -> None:
        r = self._reveal
        lvl = self._hover_level
        ids = self._ids
        self.itemconfigure(ids["avatar"], image=self._img("avatar", self._avatar_pil, r))
        # hover-only icons fade with the hover level, a favourite star is always visible
        fav = self._fav
        star_pil = gfx.icon("star_fill" if fav else "star", 20, pick(theme.WARN if fav else theme.MUTED))
        self.itemconfigure(ids["star"], image=self._img("star_fill" if fav else "star", star_pil, (1.0 if fav else lvl) * r))
        if self._has_copy:
            cp = gfx.icon("copy", 19, pick(theme.PRIMARY))
            self.itemconfigure(ids["copy"], image=self._img("copy", cp, lvl * r))
        else:
            self.itemconfigure(ids["copy"], image="")
        if "badge" in ids:
            self.itemconfigure(ids["badge"], image=self._img("badge", self._badge_pil, r))
        bg = pick(theme.CARD_SOFT)
        self.itemconfigure(ids["title"], fill=anim.lerp_hex(bg, self.title_color or pick(theme.TEXT), r))
        self.itemconfigure(ids["sub"], fill=anim.lerp_hex(bg, pick(theme.MUTED), r))

    def _set_reveal(self, t: float) -> None:
        self._reveal = t
        dx = int((1 - t) * S(16))
        self._slide(dx)
        self._apply_dynamic()
        if self._fader and self._fader.cur is not None and t < 1.0:
            self.itemconfigure(self._fader.item, image=self._reveal_bg(t))

    def _reveal_bg(self, t: float):
        a = round(t * 8) / 8
        ck = ("bg", self._state(), a)
        if ck not in self._icon_cache:
            ph = gfx.photo(anim.with_alpha(self._fader._pil(self._state()), a))
            self._keep.append(ph)
            self._icon_cache[ck] = ph
        return self._icon_cache[ck]

    def _slide(self, dx: int) -> None:
        """Position the moving parts so they sit `dx` pixels to the right of their resting place."""
        moved = getattr(self, "_dx", 0)
        delta = dx - moved
        if delta:
            for key in ("avatar", "title", "sub", "badge", "star", "copy"):
                if key in self._ids:
                    self.move(self._ids[key], delta, 0)
            self._dx = dx
        if dx == 0 and self._fader and self._fader.photo is not None:
            self.itemconfigure(self._fader.item, image=self._fader.photo)

    def _set_hover(self, value: bool) -> None:
        if value == self.hover or not self._cw:
            return
        self.hover = value
        if self._fader:
            self._fader.go(self._state(), 150 if value else 240)
        start = self._hover_level
        goal = 1.0 if value else 0.0

        def step(t: float) -> None:
            self._hover_level = start + (goal - start) * t
            self._apply_dynamic()
        anim.start(("rowhover", id(self)), 170, step, ease=anim.ease_out)

    def set_selected(self, value: bool) -> None:
        if value != self.selected:
            self.selected = value
            if self._fader:
                self._fader.go(self._state(), 220)

    # ---------------------------------------------------------------- clicks
    def _zone_at(self, x, y):
        for name, (x0, y0, x1, y1) in self._zones.items():
            if name == "copy" and not self._has_copy:
                continue
            if name in ("star", "copy") and self._hover_level < 0.35 and not (name == "star" and self._fav):
                continue
            if x0 <= x <= x1 and y0 <= y <= y1:
                return name
        return None

    def _click(self, e) -> None:
        if not (0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()):
            return
        zone = self._zone_at(e.x, e.y)
        if zone == "star":
            self.on_star(self.item)
        elif zone == "copy":
            self.on_copy(self.item)
        else:
            self.on_open(self.item)

    def destroy(self):
        anim.cancel(("row", id(self)))
        anim.cancel(("rowhover", id(self)))
        if self._fader:
            self._fader.destroy()
        for ph in self._keep:
            gfx.release(ph)
        super().destroy()
