"""Soft animation toolkit: one shared 60 fps ticker, easing curves, image fades and cross-fades.

Everything honours the "Animations" switch in Settings (when off, changes are instant).
"""
from __future__ import annotations

import sys
import time
import tkinter as tk

import customtkinter as ctk
from PIL import Image, ImageGrab

from . import gfx

FRAME_MS = 15

# ---------------------------------------------------------------------- easings
def linear(t: float) -> float:
    return t


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return t * t * (3 - 2 * t)


def ease_out_back(t: float) -> float:
    c1, c3 = 1.35, 2.35
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2


# ----------------------------------------------------------------------- engine
_root: tk.Misc | None = None
_enabled = lambda: True  # noqa: E731
_tweens: dict = {}
_job = None


def init(root, enabled) -> None:
    global _root, _enabled
    _root, _enabled = root, enabled


_icon_enabled = None


def init_icons(fn) -> None:
    global _icon_enabled
    _icon_enabled = fn


def icon_motion() -> bool:
    try:
        return bool(_icon_enabled()) if _icon_enabled else False
    except Exception:
        return False


def enabled() -> bool:
    try:
        return bool(_enabled())
    except Exception:  # noqa: BLE001
        return True


def start(key, duration_ms: float, fn, done=None, ease=ease_out, delay_ms: float = 0.0) -> None:
    """Run fn(eased_progress 0..1) every frame. A tween with the same key replaces the running one."""
    if _root is None or not enabled():
        _tweens.pop(key, None)
        try:
            fn(1.0)
            if done:
                done()
        except tk.TclError:
            pass
        return
    _tweens[key] = [time.perf_counter() + delay_ms / 1000.0, duration_ms / 1000.0, fn, done, ease]
    _ensure_running()


def cancel(key) -> None:
    _tweens.pop(key, None)


def running(key) -> bool:
    return key in _tweens


def _ensure_running() -> None:
    global _job
    if _job is None and _root is not None:
        _job = _root.after(FRAME_MS, _tick)


def _tick() -> None:
    global _job
    _job = None
    now = time.perf_counter()
    for key in list(_tweens):
        tw = _tweens.get(key)
        if tw is None:
            continue
        t0, dur, fn, done, ease = tw
        if now < t0:
            continue
        p = 1.0 if dur <= 0 else min(1.0, (now - t0) / dur)
        try:
            fn(ease(p))
            if p >= 1.0:
                if _tweens.get(key) is tw:
                    del _tweens[key]
                if done:
                    done()
        except tk.TclError:                # the widget was destroyed mid-animation
            _tweens.pop(key, None)
        except Exception:  # noqa: BLE001
            _tweens.pop(key, None)
            raise
    if _tweens:
        _ensure_running()


# ------------------------------------------------------------------ image fades
def with_alpha(img: Image.Image, alpha: float) -> Image.Image:
    """Copy of an RGBA image with its opacity multiplied by alpha (0..1)."""
    if alpha >= 0.999:
        return img
    out = img.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, alpha))))
    return out


def lerp_hex(a: str, b: str, t: float) -> str:
    ca, cb = gfx.hex_rgb(a), gfx.hex_rgb(b)
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(ca, cb))


class Fader:
    """Cross-fades a canvas image item between named states (hover, pressed, selected ...)."""

    def __init__(self, canvas: tk.Canvas, item: int, render):
        self.canvas, self.item, self.render = canvas, item, render
        self.pils: dict[str, Image.Image] = {}
        self.state: str | None = None
        self.cur: Image.Image | None = None
        self.photo = None
        self.key = ("fader", id(self), item)

    def invalidate(self) -> None:
        cancel(self.key)
        self.pils.clear()
        self.state = None

    def _pil(self, state: str) -> Image.Image:
        if state not in self.pils:
            self.pils[state] = self.render(state)
        return self.pils[state]

    def _show(self, img: Image.Image) -> None:
        old = self.photo
        self.photo = gfx.photo(img)
        self.cur = img
        self.canvas.itemconfigure(self.item, image=self.photo)
        if old is not None:
            gfx.release(old)

    def set(self, state: str) -> None:
        """Switch instantly."""
        cancel(self.key)
        self.state = state
        self._show(self._pil(state))

    def go(self, state: str, ms: float = 160) -> None:
        if state == self.state:
            return
        if self.cur is None or not enabled():
            self.set(state)
            return
        target = self._pil(state)
        start_img = self.cur
        self.state = state
        if start_img.size != target.size:
            self.set(state)
            return

        def step(t: float) -> None:
            self._show(target if t >= 1.0 else Image.blend(start_img, target, t))
        start(self.key, ms, step, ease=ease_in_out)

    def destroy(self) -> None:
        cancel(self.key)
        if self.photo is not None:
            gfx.release(self.photo)
            self.photo = None


# ------------------------------------------------------------------- cross-fade
def _grab(widget: tk.Misc, inset: int) -> Image.Image | None:
    widget.update_idletasks()
    x, y = widget.winfo_rootx() + inset, widget.winfo_rooty() + inset
    w, h = widget.winfo_width() - 2 * inset, widget.winfo_height() - 2 * inset
    if w < 40 or h < 40:
        return None
    try:
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=sys.platform.startswith("win")).convert("RGB")
    except Exception:  # noqa: BLE001
        return None


def crossfade(widget: tk.Misc, swap, ms: float = 260, inset: int = 0) -> None:
    """Run swap() and fade from the old picture of `widget` to the new one.

    Falls back to a plain swap() whenever animations are off or the screen cannot be captured.
    """
    if not enabled() or _root is None or not widget.winfo_viewable() or widget.winfo_toplevel().state() == "iconic":
        swap()
        return
    old = _grab(widget, inset)
    swap()
    if old is None:
        return
    widget.update_idletasks()
    widget.update()
    new = _grab(widget, inset)
    if new is None or new.size != old.size:
        return
    overlay = tk.Canvas(widget, highlightthickness=0, bd=0, width=old.width, height=old.height)
    overlay.place(x=inset, y=inset, width=old.width, height=old.height)
    holder = {"photo": None}
    item = overlay.create_image(0, 0, anchor="nw")
    key = ("crossfade", id(overlay))

    def show(img: Image.Image) -> None:
        prev = holder["photo"]
        holder["photo"] = gfx.photo(img)
        overlay.itemconfigure(item, image=holder["photo"])
        if prev is not None:
            gfx.release(prev)

    show(old)

    def step(t: float) -> None:
        show(Image.blend(old, new, t))

    def finish() -> None:
        try:
            overlay.destroy()
        finally:
            if holder["photo"] is not None:
                gfx.release(holder["photo"])
                holder["photo"] = None

    start(key, ms, step, done=finish, ease=ease_in_out)


# ----------------------------------------------------------------- smooth scroll
class SmoothScrollFrame(ctk.CTkScrollableFrame):
    """CTkScrollableFrame whose mouse wheel glides instead of jumping."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # CTk sets a 30 px scroll step, so the last few pixels of a page could never be reached. Scroll per pixel.
        self._parent_canvas.configure(yscrollincrement=1)
        self._target: float | None = None
        self._scroll_key = ("scroll", id(self))

    def _mouse_wheel_all(self, event):  # noqa: N802 (CTk naming)
        if not self._check_if_valid_scroll(event.widget) or getattr(self, "_shift_pressed", False):
            return super()._mouse_wheel_all(event)
        if sys.platform.startswith("linux"):
            notches = 1 if event.num == 5 else -1
        else:
            notches = -event.delta / (1.0 if sys.platform == "darwin" else 120.0)
        self.scroll_notches(notches)
        return None

    def scroll_notches(self, notches: float) -> None:
        """Glide the page by `notches` mouse-wheel clicks (positive = down). Always stops exactly at the ends."""
        canvas = self._parent_canvas
        first, last = canvas.yview()
        if (first, last) == (0.0, 1.0):
            return
        region = str(canvas.cget("scrollregion")).split()
        total = float(region[3]) - float(region[1]) if len(region) == 4 else 0.0
        if total <= 1:
            bbox = canvas.bbox("all")
            total = float((bbox[3] - bbox[1]) if bbox else 1)
        max_first = max(0.0, 1.0 - (last - first))
        base = self._target if (self._target is not None and running(self._scroll_key)) else first
        target = min(max(0.0, base + notches * gfx.S(86) / total), max_first)
        self._target = target
        begin = first

        def step(t: float) -> None:
            pos = begin + (target - begin) * t
            if abs(pos - canvas.yview()[0]) > 1e-4:   # skip redundant redraws
                canvas.yview_moveto(pos)
        start(self._scroll_key, 260, step, ease=ease_out)
