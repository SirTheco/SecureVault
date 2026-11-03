"""Hero panel with gently drifting tiles and a smooth padlock transition."""
from __future__ import annotations

import math
import time
import tkinter as tk

from PIL import Image, ImageDraw

from . import anim, gfx, theme
from .gfx import S
from .theme import pick
from .widgets import GButton, _darken

# Match the existing light Graphite theme's blue artwork in every palette.
SCENE_ICON_TINT = "#5B6069"
UNLOCK_SECONDS = 1.15
UNLOCK_PAUSE_MS = 500
UNLOCK_ANGLE = 0.0
UNLOCK_LIFT = 0.05
RIGHT_LEG_EXTENSION = 0.07

# name, sprite, x, y (fractions of the panel), width (fraction of min(W, H)), bob amplitude, speed, phase, depth
FLOATERS = [
    ("cloud_l", "cloud", 0.15, 0.60, 0.36, 3, 0.35, 0.0, 0.35, "cloud"),
    ("cloud_r", "cloud", 0.88, 0.30, 0.27, 3, 0.30, 2.0, 0.30, "cloud"),
    ("t_cloud", "tile_cloud", 0.17, 0.15, 0.24, 7, 1.10, 0.3, 0.9, "tile"),
    ("t_key", "tile_key", 0.13, 0.46, 0.19, 6, 1.25, 3.1, 0.8, "tile"),
    ("t_card", "tile_card", 0.88, 0.50, 0.20, 7, 0.95, 4.4, 1.0, "tile"),
    ("t_mail", "tile_mail", 0.76, 0.69, 0.17, 6, 1.15, 5.2, 0.7, "tile"),
    ("t_user", "tile_user", 0.19, 0.69, 0.17, 6, 1.05, 2.6, 0.75, "tile"),
    ("o_pink", "orb_pink", 0.69, 0.07, 0.075, 5, 1.4, 1.0, 1.3, "orb"),
    ("o_teal", "orb_teal", 0.24, 0.26, 0.055, 4, 1.2, 3.7, 1.4, "orb"),
    ("o_orange", "orb_orange", 0.78, 0.60, 0.05, 4, 1.3, 0.6, 1.2, "orb"),
]


def ease(p: float) -> float:
    return p * p * (3 - 2 * p)


def smootherstep(p: float) -> float:
    """Ease with zero velocity and acceleration at both endpoints."""
    p = min(1.0, max(0.0, p))
    return p * p * p * (p * (p * 6.0 - 15.0) + 10.0)


def unlock_pose(progress: float) -> tuple[float, float]:
    """Raise the whole shackle straight up, without rotating it."""
    p = min(1.0, max(0.0, progress))
    return UNLOCK_ANGLE, UNLOCK_LIFT * smootherstep(p)


def _lift_shackle(image: Image.Image, pivot_x: float, lift_px: float, padding: int) -> Image.Image:
    """Translate the arch upward without tilting or deforming it."""
    return image.transform(
        (image.width, image.height + 2 * padding), Image.Transform.AFFINE,
        (1, 0, 0, 0, 1, -padding + lift_px),
        resample=Image.Resampling.BICUBIC,
    )


def _turn_shackle(image: Image.Image, pivot_x: float, angle: float) -> tuple[Image.Image, float]:
    """Project a vertical-axis half-turn, returning the image and hinge position.

    The arch remains upright. Its free leg swings to the right of the hinge,
    rather than rotating down into the body of the lock.
    """
    projection = math.cos(math.radians(angle))
    width = max(1, round(image.width * abs(projection)))
    frame = image.resize((width, image.height), Image.Resampling.LANCZOS)
    hinge_x = pivot_x * width / image.width
    if projection < 0:
        frame = frame.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        hinge_x = width - hinge_x
    return frame, hinge_x


def _split_shackle(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Keep the collars still and extend the right leg behind the lock body."""
    cut = round(image.height * (420 / 1090))
    arch = image.copy()
    arch.paste((0, 0, 0, 0), (0, cut, image.width, image.height))
    # Continue the existing silver texture downward. The collars and body are
    # drawn in front, so the extra length stays hidden until the arch rises.
    x0 = round(image.width * (640 / 1090))
    x1 = round(image.width * (790 / 1090))
    extension = max(1, round(image.height * RIGHT_LEG_EXTENSION))
    extension = min(extension, image.height - cut)
    if extension > 0:
        strip = image.crop((x0, max(0, cut - 2), x1, max(0, cut - 2) + 1))
        strip = strip.resize((x1 - x0, extension), Image.Resampling.NEAREST)
        arch.paste(strip, (x0, cut))
    collars = image.copy()
    collars.paste((0, 0, 0, 0), (0, 0, image.width, cut))
    return arch, collars


class HeroScene(tk.Canvas):
    def __init__(self, master, bg, title: str, subtitle: str, button: tuple | None = None, animate=lambda: True,
                 radius: int = 34, compact: bool = False):
        self.bg_pair = bg
        self.title, self.subtitle, self.button_spec = title, subtitle, button
        self.animate, self.radius, self.compact = animate, radius, compact
        super().__init__(master, bg=pick(bg), highlightthickness=0, bd=0)
        self._size = (0, 0)
        self._relayout_job = None
        self._tick_job = None
        self._items: list[dict] = []
        self._photos: list = []
        self._t0 = time.monotonic()
        self._motion_active = False
        self._par = [0.0, 0.0]
        self._shake_t0 = None
        self._open = None          # [start_time, callback, callback_scheduled]
        self._opened = False
        self._unlock_callback_job = None
        self._open_frame_ph = None
        self._open_frame_angle = None
        self._open_frame_hinge_x = None
        self._open_frame_lift = None
        self._entered = False       # the soft "objects rise into place" entrance has played
        self._born = 0.0
        self._entering = False
        self._button = None
        self.bg_provider = None      # optional: callable returning the RGB backdrop behind the panel (for perfect corners)
        self.bind("<Configure>", self._on_configure)
        self.bind("<Button-1>", self._on_press, add="+")
        self._tick()

    # ---------------------------------------------------------------- layout
    def force_layout(self) -> None:
        self._size = (0, 0)
        self._layout()

    def _on_configure(self, event):
        if (event.width, event.height) == self._size:
            return
        if self._relayout_job:
            self.after_cancel(self._relayout_job)
        self._relayout_job = self.after(1 if self._size == (0, 0) else 60, self._layout)

    def _keep(self, img):
        ph = gfx.photo(img)
        self._photos.append(ph)
        return ph

    def _layout(self):
        self._relayout_job = None
        wp, hp = self.winfo_width(), self.winfo_height()
        if wp < 60 or hp < 60:
            return
        self._size = (wp, hp)
        for ph in self._photos:
            gfx.release(ph)
        self._photos.clear()
        self._open_frame_ph = None
        self._open_frame_angle = None
        self._open_frame_hinge_x = None
        self._open_frame_lift = None
        self._items.clear()
        self.delete("all")
        sc = gfx.scale()
        W, H = wp / sc, hp / sc
        self._W = W
        # panel
        accent_a, accent_b = theme.PRIMARY_GRAD
        if theme.dark():
            accent_a, accent_b = accent_b, accent_a
        panel = gfx.panel_image(wp, hp, accent_a, accent_b, S(self.radius), angle=62)
        if self.bg_provider is not None:
            try:
                backdrop = self.bg_provider(wp, hp)
                if backdrop is not None and backdrop.size == (wp, hp):
                    backdrop = backdrop.convert("RGBA")
                    backdrop.alpha_composite(panel)
                    panel = backdrop
            except Exception:  # noqa: BLE001
                pass
        self.create_image(0, 0, anchor="nw", image=self._keep(panel))
        u = min(W, H * 0.95)
        # soft ground shadow under the padlock
        pad_h = H * (0.50 if not self.compact else 0.46)
        cx, cy = W * 0.5, H * 0.43
        shadow = gfx.soft_blob((int(S(pad_h * 0.62)), int(S(pad_h * 0.10))), "#2A1580", 0.45, S(10))
        self._add("shadow", self._keep(shadow), cx, cy + pad_h * 0.43, 0, 0, 0, 0.2, kind="shadow")
        for name, spr, fx, fy, fw, amp, speed, phase, depth, kind in FLOATERS:
            if kind == "tile" and self.compact and name in ("t_mail", "t_user"):
                continue
            wlog = fw * u / (0.72 if kind == "tile" else 0.62 if kind == "cloud" else 0.80)
            img = (gfx.sprite(spr, width=wlog, tint=SCENE_ICON_TINT)
                   if kind == "tile" else gfx.sprite(spr, width=wlog))
            self._add(name, self._keep(img), W * fx, H * fy, amp, speed, phase, depth, kind=kind)
            self._items[-1]["half"] = img.width / gfx.scale() / 2   # clouds wrap only once fully off-canvas
        # padlock (shackle sits behind the body)
        body = gfx.sprite("padlock_body", height=pad_h / 0.84)
        shackle = gfx.sprite("padlock_shackle", height=pad_h / 0.84)
        arch, collars = _split_shackle(shackle)
        self._pad_h_img = pad_h / 0.84
        # The moving arch is cropped separately from the fixed collars.
        pivot = (shackle.width * (718 / 1090), shackle.height * (420 / 1090))
        x0, y0, x1, y1 = arch.getbbox()
        bounds = (x0 - 3, y0 - 3, x1 + 3, y1 + 3)
        self._arch_image = arch.crop(bounds)
        self._arch_height = shackle.height
        self._lift_padding = math.ceil(self._arch_height * UNLOCK_LIFT * 2) + 3
        self._arch_pivot = (pivot[0] - bounds[0], pivot[1] - bounds[1])
        self._arch_center_offset = (bounds[0] + self._arch_image.width / 2 - shackle.width / 2,
                                    bounds[1] + self._arch_image.height / 2 - shackle.height / 2)
        self._shackle_ph = self._keep(arch)
        self._add("shackle", self._shackle_ph, cx, cy, 5, 1.0, 0.0, 0.6, kind="pad")
        self._add("collars", self._keep(collars), cx, cy, 5, 1.0, 0.0, 0.6, kind="pad")
        self._add("body", self._keep(body), cx, cy, 5, 1.0, 0.0, 0.6, kind="pad")
        # sparkles
        self._sparks = []
        for fx, fy, sz, ph in (() if True else ((0.08, 0.30, 7, 0.0), (0.93, 0.40, 6, 1.5), (0.45, 0.07, 6, 2.4), (0.24, 0.52, 5, 3.3),
                               (0.75, 0.25, 5, 4.1), (0.60, 0.62, 5, 5.0))):
            a = self.create_line(0, 0, 0, 0, width=S(2), capstyle="round", fill="#FFFFFF")
            b = self.create_line(0, 0, 0, 0, width=S(2), capstyle="round", fill="#FFFFFF")
            self._sparks.append((a, b, fx * W, fy * H, sz, ph))
        # caption card
        cap_h = H * (0.20 if not self.button_spec else 0.22)
        cap_w = W * 0.86
        cap = self._caption_image(int(S(cap_w)), int(S(cap_h)))
        cap_y = H * 0.975 - cap_h
        self._cap_xy = (W * 0.07, cap_y)
        self._btn_win = None
        self._cap_id = self.create_image(S(W * 0.07), S(cap_y), anchor="nw", image=self._keep(cap))
        if self.button_spec:
            if self._button is not None:
                self._button.destroy()
            text, command = self.button_spec
            # A Tk canvas cannot be transparent. Paint the exact caption
            # beneath the button so its rounded corners blend into the gradient.
            button_right = S(W * 0.07 + cap_w - 18)
            button_center_y = S(cap_y + cap_h / 2)
            bg_x = button_right - S(150) - S(W * 0.07)
            bg_y = button_center_y - S(40) // 2 - S(cap_y)
            button_bg = cap.crop((bg_x, bg_y, bg_x + S(150), bg_y + S(40)))
            self._button = GButton(self, text, command, width=150, height=40, style="white", icon="plus", bg=None,
                                   size=13, background_image=button_bg,
                                   label_color=_darken(pick(theme.PRIMARY), 0.28) if theme.dark() else None)
            sample = cap.getpixel((max(0, cap.width - S(18) - S(75)), cap.height // 2))
            self._button.configure(bg="#%02x%02x%02x" % sample[:3])
            self._btn_win = self.create_window(S(W * 0.07 + cap_w - 18), S(cap_y + cap_h / 2), anchor="e",
                                               window=self._button)
        # Start at the artwork's resting positions, without an entrance bounce.
        self._entered = True
        self._entering = False
        self._apply(0.0)

    def _add(self, name, ph, x, y, amp, speed, phase, depth, kind):
        item = self.create_image(S(x), S(y), anchor="center", image=ph)
        n = len(self._items)
        delay = 0.10 if kind in ("pad", "shadow") else 0.22 + n * 0.055
        self._items.append(dict(name=name, item=item, x=x, y=y, amp=amp, speed=speed, phase=phase, depth=depth,
                                kind=kind, delay=delay, hov=0.0, press=None))

    def _caption_image(self, w: int, h: int) -> Image.Image:
        cap_a, cap_b = theme.TEAL_GRAD
        if theme.dark():
            cap_a, cap_b = cap_b, cap_a
        img = gfx.panel_image(w, h, cap_a, cap_b, S(28), angle=15, blobs=False)
        deco = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(deco)
        d.ellipse((w - h * 0.9, -h * 0.35, w + h * 0.1, h * 0.65), fill=(255, 255, 255, 38))
        d.ellipse((w - h * 1.5, h * 0.55, w - h * 0.6, h * 1.45), fill=(255, 255, 255, 26))
        img = Image.alpha_composite(img, deco)
        mask = gfx.rounded_mask((w, h), S(28))
        title = gfx.text_image(self.title, 19 if not self.compact else 17, "#FFFFFF", "bold", max_width=int(w / gfx.scale() * (0.52 if self.button_spec else 0.8)))
        sub = gfx.text_image(self.subtitle, 11, "#F8F8FC", "regular", max_width=int(w / gfx.scale() * (0.52 if self.button_spec else 0.8)), line_spacing=1.35)
        total = title.height + S(4) + (sub.height if self.subtitle else 0)
        y = (h - total) // 2
        img.alpha_composite(title, (S(22), y))
        if self.subtitle:
            img.alpha_composite(sub, (S(22), y + title.height + S(2)))
        img.putalpha(mask)
        return img

    # --------------------------------------------------------------- animation
    def _icons_on(self) -> bool:
        return anim.enabled() and anim.icon_motion()

    def _pointer(self):
        try:
            return self.winfo_pointerx() - self.winfo_rootx(), self.winfo_pointery() - self.winfo_rooty()
        except tk.TclError:
            return -1, -1

    def _hit(self, it, px, py) -> bool:
        box = self.bbox(it["item"])
        if not box:
            return False
        x1, y1, x2, y2 = box
        return x1 <= px <= x2 and y1 <= py <= y2

    def _on_press(self, e):
        if not self._icons_on():
            return
        for it in self._items:
            if it["kind"] in ("tile", "orb") and self._hit(it, e.x, e.y):
                it["press"] = time.monotonic()

    def _apply(self, t: float):
        moving = self.animate() and anim.enabled()
        icons = self._icons_on()
        now = time.monotonic()
        shake_dx = 0.0
        shake_t0 = getattr(self, "_shake_t0", None)
        if shake_t0 is not None:
            age = now - shake_t0
            if moving and age < 0.48:
                shake_dx = 8.0 * (1.0 - age / 0.48) * math.sin(age * 42.0)
            else:
                self._shake_t0 = None
        px, py = self._pointer() if icons else (-1, -1)
        for it in self._items:
            if it["name"] == "shackle" and self._open is not None:
                continue
            # Tiles float slowly; the lock only moves for an error animation.
            dx = dy = 0.0
            if it["kind"] == "pad":
                dx = shake_dx
            if moving and it["kind"] in ("tile", "orb"):
                phase = it["phase"]
                dy = 1.8 * (math.sin(t * 0.55 + phase) - math.sin(phase))
            if moving and it["kind"] == "cloud":
                # endless drift: wrap past both edges so the loop never visibly restarts
                half = it.get("half", 0.0)
                span = self._W + 2 * half
                x_now = (it["x"] + 8.0 * it["speed"] * t + half) % span - half
                self.coords(it["item"], x_now * gfx.scale(), it["y"] * gfx.scale())
                continue
            if icons and it["kind"] in ("tile", "orb"):
                target = 1.0 if self._hit(it, px, py) else 0.0
                it["hov"] += (target - it["hov"]) * 0.18
                h = it["hov"]
                if h > 0.01:
                    dy -= 6.0 * h
                    dx += 2.5 * h * math.sin(now * 6.0 + it["phase"])
                if it["press"] is not None:
                    age = now - it["press"]
                    if age < 0.8:
                        env = math.exp(-age * 4.5)
                        dx += 9.0 * env * math.sin(age * 32.0)
                        dy -= 8.0 * env * abs(math.sin(age * 10.0))
                    else:
                        it["press"] = None
            self.coords(it["item"], (it["x"] + dx) * gfx.scale(), (it["y"] + dy) * gfx.scale())
        for a, b, x, y, size, ph in self._sparks:
            r = S(size) * 0.72
            cx, cy = S(x), S(y)
            self.coords(a, cx - r, cy, cx + r, cy)
            self.coords(b, cx, cy - r, cx, cy + r)

    def _tick(self):
        self._tick_job = self.after(16, self._tick)
        try:
            if not self.winfo_viewable() or not self._items:
                return
            if self._open is not None:
                self._step_open()
            if (self.animate() and anim.enabled()) or self._icons_on():
                self._apply(time.monotonic() - self._t0)
                self._motion_active = True
            elif self._motion_active:
                self._apply(0.0)
                self._motion_active = False
        except tk.TclError:
            pass

    # -------------------------------------------------------- public animations
    def shake(self) -> None:
        """Briefly shake the whole lock for an incorrect password."""
        if self.animate() and anim.enabled() and self._open is None:
            self._shake_t0 = time.monotonic()

    def reset_lock(self) -> None:
        if self._unlock_callback_job is not None:
            self.after_cancel(self._unlock_callback_job)
            self._unlock_callback_job = None
        self._open = None
        self._opened = False
        self._shake_t0 = None
        for it in self._items:
            if it["name"] == "shackle":
                self.itemconfigure(it["item"], image=self._shackle_ph)
                self.coords(it["item"], it["x"] * gfx.scale(), it["y"] * gfx.scale())
        if self._open_frame_ph is not None:
            gfx.release(self._open_frame_ph)
            if self._open_frame_ph in self._photos:
                self._photos.remove(self._open_frame_ph)
        self._open_frame_ph = None
        self._open_frame_angle = None
        self._open_frame_hinge_x = None
        self._open_frame_lift = None

    def play_unlock(self, callback) -> None:
        """Animate the padlock opening, then call callback()."""
        if self._open is not None:
            return
        if self._opened or not self._items:
            callback()
            return
        if not self.animate() or not anim.enabled():
            callback()
            return
        self._shake_t0 = None
        self._open = [time.monotonic(), callback, False]
        self._opened = True
        self._step_open()

    def _step_open(self):
        start, callback, done_flag = self._open
        p = min(1.0, max(0.0, (time.monotonic() - start) / UNLOCK_SECONDS))
        # Lift the entire arch straight up, then hold it before entering.
        angle, lift = unlock_pose(p)
        angle = round(angle, 2)
        lift_px = round(self._arch_height * lift, 3)
        it = next(x for x in self._items if x["name"] == "shackle")
        if angle != self._open_frame_angle or lift_px != self._open_frame_lift:
            raised = _lift_shackle(self._arch_image, self._arch_pivot[0], lift_px, self._lift_padding)
            frame, self._open_frame_hinge_x = _turn_shackle(raised, self._arch_pivot[0], angle)
            new_ph = self._keep(frame)
            self.itemconfigure(it["item"], image=new_ph)
            if self._open_frame_ph is not None:
                gfx.release(self._open_frame_ph)
                if self._open_frame_ph in self._photos:
                    self._photos.remove(self._open_frame_ph)
            self._open_frame_ph = new_ph
            self._open_frame_angle = angle
            self._open_frame_lift = lift_px
        hinge_world_x = (it["x"] * gfx.scale() + self._arch_center_offset[0]
                         - self._arch_image.width / 2 + self._arch_pivot[0])
        frame_width = max(1, round(self._arch_image.width * abs(math.cos(math.radians(angle)))))
        self.coords(it["item"], hinge_world_x - self._open_frame_hinge_x + frame_width / 2,
                    it["y"] * gfx.scale() + self._arch_center_offset[1])
        if p >= 1.0 and not done_flag:
            self._open[2] = True
            def finish():
                self._unlock_callback_job = None
                callback()
            self._unlock_callback_job = self.after(UNLOCK_PAUSE_MS, finish)

    def destroy(self):
        for job in (self._tick_job, self._relayout_job, self._unlock_callback_job):
            if job:
                try:
                    self.after_cancel(job)
                except tk.TclError:
                    pass
        for ph in self._photos:
            gfx.release(ph)
        super().destroy()


class Backdrop(tk.Canvas):
    """Full-window soft gradient with blurred colour blobs (behind the login card and hero panel)."""

    def __init__(self, master, on_resize=None):
        super().__init__(master, bg=pick(theme.PAGE), highlightthickness=0, bd=0)
        self.on_resize = on_resize
        self._job = None
        self._size = (0, 0)
        self._ph = None
        self._pil = None
        self._item = self.create_image(0, 0, anchor="nw")
        self.bind("<Configure>", self._on_configure)

    def _on_configure(self, event):
        if (event.width, event.height) == self._size:
            return
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(50, self._render)

    def _render(self):
        self._job = None
        w, h = self.winfo_width(), self.winfo_height()
        if w < 50 or h < 50:
            return
        self._size = (w, h)
        c1, c2 = pick(theme.PAGE), pick(theme.CARD_SOFT)
        accent = pick(theme.PRIMARY)
        teal = theme.TEAL_GRAD[1 if theme.dark() else 0]
        if theme.dark():
            blobs = ((accent, 0.28), (teal, 0.14))
        else:
            blobs = ((accent, 0.22), (teal, 0.16))
        img = gfx.gradient((w, h), c1, c2, 62).convert("RGBA")
        b1 = gfx.soft_blob((int(w * 0.45), int(w * 0.45)), blobs[0][0], blobs[0][1], w * 0.07)
        img.alpha_composite(b1, (int(w * 0.80), int(h * 0.62)))
        b2 = gfx.soft_blob((int(w * 0.35), int(w * 0.35)), blobs[1][0], blobs[1][1], w * 0.07)
        img.alpha_composite(b2, (-int(w * 0.14), -int(w * 0.14)))
        self._pil = img.convert("RGB")
        old = self._ph
        self._ph = gfx.photo(self._pil)
        self.itemconfigure(self._item, image=self._ph)
        if old is not None:
            gfx.release(old)
        if self.on_resize:
            self.on_resize(w, h)

    def color_at(self, x: int, y: int) -> str:
        if self._pil is None:
            return pick(theme.PAGE)
        x = max(0, min(self._pil.width - 1, int(x)))
        y = max(0, min(self._pil.height - 1, int(y)))
        return "#%02x%02x%02x" % self._pil.getpixel((x, y))
