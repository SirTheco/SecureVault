"""Runtime graphics: fonts, DPI scale, vector icons, gradients, avatars, sprites.

Everything is drawn with Pillow and cached.  Sizes passed to the public
helpers are "logical" pixels; they are multiplied by the current UI scale so
the artwork stays sharp on high-DPI screens.
"""
from __future__ import annotations

import hashlib
import math
import re
import sys
import tkinter.font as tkfont
from functools import lru_cache
from pathlib import Path

import customtkinter as ctk
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageTk

from . import theme
from .clay import clay, hex_rgb, new_mask

RESAMPLE = Image.Resampling.LANCZOS
SHADOW_PAD = 48
_scale = 1.0
_photos: dict = {}           # keeps PhotoImage objects alive
_font_ok = False
FONT_FILES = {"regular": "Poppins-Regular.ttf", "medium": "Poppins-Medium.ttf", "bold": "Poppins-Bold.ttf"}


# ------------------------------------------------------------------ resources
def asset_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base.joinpath("assets", *parts)


def init(root) -> None:
    """Call once after the root window exists."""
    global _scale, _font_ok
    try:
        _scale = float(ctk.ScalingTracker.get_widget_scaling(root))
    except Exception:  # noqa: BLE001
        try:
            _scale = float(root.winfo_fpixels("1i")) / 96.0
        except Exception:  # noqa: BLE001
            _scale = 1.0
    for name in FONT_FILES.values():
        try:
            ctk.FontManager.load_font(str(asset_path("fonts", name)))
        except Exception:  # noqa: BLE001
            pass
    try:
        _font_ok = "Poppins" in tkfont.families(root)
    except Exception:  # noqa: BLE001
        _font_ok = False
    if not _font_ok:
        theme.FONT_FAMILY = theme.FONT_MEDIUM = "Segoe UI" if sys.platform.startswith("win") else "Helvetica"


def scale() -> float:
    return _scale


def S(value: float) -> int:
    """Logical -> physical pixels."""
    return max(1, int(round(value * _scale))) if value else 0


def photo(img: Image.Image) -> ImageTk.PhotoImage:
    ph = ImageTk.PhotoImage(img)
    _photos[id(ph)] = ph
    return ph


def release(ph) -> None:
    _photos.pop(id(ph), None)


def tkfont_for(size: int, weight: str = "normal") -> tkfont.Font:
    family = theme.FONT_MEDIUM if weight == "medium" else theme.FONT_FAMILY
    return tkfont.Font(family=family, size=-S(size), weight="bold" if weight == "bold" else "normal")


@lru_cache(maxsize=64)
def pil_font(size_px: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(asset_path("fonts", FONT_FILES.get(weight, FONT_FILES["regular"]))), size_px)
    except OSError:
        return ImageFont.load_default()


# --------------------------------------------------------------------- sprites
@lru_cache(maxsize=None)
def _base_sprite(name: str) -> Image.Image:
    return Image.open(asset_path("sprites", f"{name}.png")).convert("RGBA")


_BASE_HUE = 161          # hue of the blue artwork on PIL's 0-255 HSV scale
_TINT_SPRITES = ("tile_", "orb_", "cloud")
_tinted: dict = {}


def _retint(im: Image.Image, target: str) -> Image.Image:
    """Shift only the blue/violet parts of the artwork toward the app's accent hue."""
    import colorsys
    r, g_, b = hex_rgb(target)
    target_hue = colorsys.rgb_to_hsv(r / 255, g_ / 255, b / 255)[0] * 256
    shift = int(round(target_hue - _BASE_HUE))
    h, sat, val = im.convert("RGB").convert("HSV").split()
    band = h.point(lambda x: 255 if 120 <= x <= 205 else 0)
    vivid = sat.point(lambda x: 255 if x > 64 else 0)
    mask = ImageChops.multiply(band, vivid)
    new_h = h.point(lambda x: (x + shift) % 256)
    out = Image.merge("HSV", (Image.composite(new_h, h, mask), sat, val)).convert("RGB")
    out.putalpha(im.getchannel("A"))
    return out


def reset_palette_cache() -> None:
    """Drop every cached, palette-tinted sprite so a new colour theme shows up immediately."""
    sprite.cache_clear()
    _avatar.cache_clear()
    _tinted.clear()


def _sprite_raw(name: str) -> Image.Image:
    from . import theme
    im = _base_sprite(name)
    if not name.startswith(_TINT_SPRITES):
        return im
    target = theme.pick(theme.PRIMARY)
    key = (name, target)
    if key not in _tinted:
        _tinted[key] = _retint(im, target)
    return _tinted[key]


@lru_cache(maxsize=256)
def sprite(name: str, width: int | None = None, height: int | None = None, rot: int = 0,
           tint: str | None = None) -> Image.Image:
    """Sprite resized so that its *content* is `width` logical px wide (padding included proportionally)."""
    # A fixed tint is useful for scene artwork that should not follow the palette.
    if tint is not None:
        key = (name, tint)
        if key not in _tinted:
            _tinted[key] = _retint(_base_sprite(name), tint)
        im = _tinted[key]
    else:
        im = _sprite_raw(name)
    if width is None and height is None:
        w, h = im.size
    elif width is not None:
        w = S(width)
        h = round(im.height * w / im.width)
    else:
        h = S(height)
        w = round(im.width * h / im.height)
    out = im.resize((max(1, w), max(1, h)), RESAMPLE)
    if rot:
        out = out.rotate(rot / 10, resample=Image.Resampling.BICUBIC, center=(out.width / 2, out.height * 0.78))
    return out


# ------------------------------------------------------------- gradients/cards
def gradient(size: tuple[int, int], c1: str, c2: str, angle: float = 90.0) -> Image.Image:
    """Linear gradient. angle 90 = top->bottom, 0 = left->right, 45 = diagonal (c1 top/left -> c2 bottom/right)."""
    w, h = size
    a, b = hex_rgb(c1), hex_rgb(c2)
    rad = math.radians(max(0.0, min(90.0, angle)))
    wy = math.sin(rad) / (math.sin(rad) + math.cos(rad))      # weight of the vertical ramp
    gy = Image.linear_gradient("L").resize((w, h), Image.Resampling.BILINEAR)
    if wy >= 0.999:
        mask = gy
    else:
        gx = Image.linear_gradient("L").rotate(90, expand=True)
        gx = gx.resize((w, h), Image.Resampling.BILINEAR)
        mask = Image.blend(gx, gy, wy)
    return Image.composite(Image.new("RGB", (w, h), b), Image.new("RGB", (w, h), a), mask)


def rounded_mask(size, radius, ss: int = 3) -> Image.Image:
    w, h = size
    m = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=255)
    return m.resize((w, h), RESAMPLE)


def soft_blob(size, color: str, opacity: float, blur: float) -> Image.Image:
    w, h = size
    pad = int(blur * 3)
    layer = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse((pad, pad, pad + w, pad + h), fill=hex_rgb(color) + (int(255 * opacity),))
    return layer.filter(ImageFilter.GaussianBlur(blur))


def panel_image(w: int, h: int, c1: str, c2: str, radius: int, angle: float = 70.0, blobs: bool = True) -> Image.Image:
    """Rounded gradient panel (px sizes) with soft light blobs, like the hero cards of the reference design."""
    img = gradient((w, h), c1, c2, angle).convert("RGBA")
    if blobs:
        a = soft_blob((int(w * 0.8), int(w * 0.8)), "#FFFFFF", 0.20, w * 0.10)
        img.alpha_composite(a, (int(-w * 0.25) - int(w * 0.1), int(-h * 0.15) - int(w * 0.1)))
        b = soft_blob((int(w * 0.7), int(w * 0.7)), "#5B3DE0", 0.35, w * 0.12)
        img.alpha_composite(b, (int(w * 0.45) - int(w * 0.12), int(h * 0.55) - int(w * 0.12)))
        img = img.crop((0, 0, w, h)) if img.size != (w, h) else img
    img.putalpha(rounded_mask((w, h), radius))
    return img


def card_image(w: int, h: int, fill: str, radius: int, border: str | None = None, shadow: float = 0.0,
               shadow_color: str = "#5B3DE0", bg: str | None = None) -> Image.Image:
    """White (or dark) rounded card, optional hairline border and soft lavender shadow."""
    pad = S(SHADOW_PAD) if shadow else 0
    base = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), hex_rgb(shadow_color) + (0,))
        sh.putalpha(rounded_mask((w, h), radius).point(lambda v: int(v * shadow)))
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        layer.alpha_composite(sh, (pad, pad + S(8)))
        base = Image.alpha_composite(base, layer.filter(ImageFilter.GaussianBlur(S(15))))
    body = Image.new("RGBA", (w, h), hex_rgb(fill) + (255,))
    body.putalpha(rounded_mask((w, h), radius))
    if border:
        ring = Image.new("RGBA", (w, h), hex_rgb(border) + (255,))
        outer = rounded_mask((w, h), radius)
        inner = Image.new("L", (w, h), 0)
        inner.paste(rounded_mask((w - 2, h - 2), max(1, radius - 1)), (1, 1))
        ring.putalpha(ImageChops.subtract(outer, inner))
        body = Image.alpha_composite(body, ring)
    base.alpha_composite(body, (pad, pad))
    return base


def gradient_pill(w: int, h: int, c1: str, c2: str, radius: int | None = None, gloss: bool = True,
                  glow: float = 0.0) -> Image.Image:
    radius = h // 2 if radius is None else radius
    pad = S(14) if glow else 0
    img = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    if glow:
        sh = Image.new("RGBA", (w, h), hex_rgb(c2) + (0,))
        sh.putalpha(rounded_mask((w, h), radius).point(lambda v: int(v * glow)))
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        layer.alpha_composite(sh, (pad, pad + S(5)))
        img = Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(S(8))))
    body = gradient((w, h), c1, c2, 90 if h >= w * 0.6 else 20).convert("RGBA")
    if gloss:
        hi = Image.new("RGBA", (w, h), (255, 255, 255, 0))
        d = ImageDraw.Draw(hi)
        d.rounded_rectangle((2, 1, w - 3, h * 0.52), radius=max(2, radius - 2), fill=(255, 255, 255, 46))
        body.alpha_composite(hi)
    body.putalpha(rounded_mask((w, h), radius))
    img.alpha_composite(body, (pad, pad))
    return img


# ------------------------------------------------------------------------ icons
def _stroke(d, pts, w, fill):
    d.line(pts, fill=fill, width=int(w), joint="curve")
    r = w / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _star(cx, cy, ro, ri):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        r = ro if i % 2 == 0 else ri
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    return pts


def _draw_icon(name: str, d: ImageDraw.ImageDraw, im: Image.Image, k: float, c) -> None:
    w = 2.0 * k            # stroke width
    P = lambda *pts: [(x * k, y * k) for x, y in pts]  # noqa: E731
    box = lambda x0, y0, x1, y1: (x0 * k, y0 * k, x1 * k, y1 * k)  # noqa: E731
    if name in ("lock", "unlock"):
        d.rounded_rectangle(box(4.8, 10.5, 19.2, 21), radius=3.6 * k, outline=c, width=int(w))
        if name == "lock":
            d.arc(box(7.5, 3, 16.5, 15), 180, 360, fill=c, width=int(w))
            _stroke(d, P((7.5, 9), (7.5, 10.8)), w, c)
            _stroke(d, P((16.5, 9), (16.5, 10.8)), w, c)
        else:
            d.arc(box(8, 2, 16, 14), 180, 360, fill=c, width=int(w))
            _stroke(d, P((8, 8), (8, 11)), w, c)
        d.ellipse(box(10.7, 13.8, 13.3, 16.4), fill=c)
        _stroke(d, P((12, 16), (12, 18)), w * 0.65, c)
    elif name == "key":
        d.ellipse(box(3.5, 11.5, 11.5, 19.5), outline=c, width=int(w))
        _stroke(d, P((10.5, 12.5), (20, 3.5)), w, c)
        _stroke(d, P((16.5, 7), (19, 9.5)), w, c)
        _stroke(d, P((13.5, 10), (15.5, 12)), w, c)
    elif name in ("star", "star_fill"):
        pts = _star(12 * k, 12.6 * k, 9.4 * k, 4.2 * k)
        if name == "star_fill":
            d.polygon(pts, fill=c)
            d.line(pts + [pts[0]], fill=c, width=int(w * 0.8), joint="curve")
        else:
            d.line(pts + [pts[0]], fill=c, width=int(w * 0.9), joint="curve")
    elif name == "copy":
        d.rounded_rectangle(box(9, 3, 20, 15), radius=3 * k, outline=c, width=int(w))
        d.rounded_rectangle(box(3.4, 8.4, 15.6, 21), radius=3 * k, fill=(0, 0, 0, 0))
        d.rounded_rectangle(box(4, 9, 15, 20.6), radius=3 * k, outline=c, width=int(w))
    elif name in ("eye", "eye_off"):
        d.arc(box(2.5, 4.5, 21.5, 19.5), 200, 340, fill=c, width=int(w))
        d.arc(box(2.5, 4.5, 21.5, 19.5), 20, 160, fill=c, width=int(w))
        d.ellipse(box(9.1, 9.1, 14.9, 14.9), outline=c, width=int(w))
        d.ellipse(box(11.1, 11.1, 12.9, 12.9), fill=c)
        if name == "eye_off":
            _stroke(d, P((4, 20), (20, 4)), w * 1.25, (0, 0, 0, 0))
            _stroke(d, P((4.4, 20), (20, 4.4)), w, c)
    elif name == "plus":
        _stroke(d, P((12, 5), (12, 19)), w * 1.15, c)
        _stroke(d, P((5, 12), (19, 12)), w * 1.15, c)
    elif name == "gear":
        pts = []
        for i in range(8):
            base = i * math.pi / 4
            for da, r in ((-0.30, 7.6), (-0.20, 10.4), (0.20, 10.4), (0.30, 7.6)):
                a = base + da
                pts.append((12 + r * math.cos(a), 12 + r * math.sin(a)))
        d.polygon(P(*pts), fill=c)
        d.ellipse(box(8.4, 8.4, 15.6, 15.6), fill=(0, 0, 0, 0))
    elif name == "search":
        d.ellipse(box(3.5, 3.5, 16.5, 16.5), outline=c, width=int(w))
        _stroke(d, P((15, 15), (20.5, 20.5)), w * 1.1, c)
    elif name == "trash":
        _stroke(d, P((4, 7), (20, 7)), w, c)
        _stroke(d, P((9, 7), (9, 4), (15, 4), (15, 7)), w, c)
        _stroke(d, P((6, 7), (7, 20), (17, 20), (18, 7)), w, c)
        _stroke(d, P((10.2, 11), (10.2, 16.5)), w * 0.9, c)
        _stroke(d, P((13.8, 11), (13.8, 16.5)), w * 0.9, c)
    elif name == "open":
        _stroke(d, P((13, 4), (20, 4), (20, 11)), w, c)
        _stroke(d, P((20, 4), (10.5, 13.5)), w, c)
        _stroke(d, P((17, 15), (17, 19.5), (4.5, 19.5), (4.5, 7), (9, 7)), w, c)
    elif name in ("shield", "shield_alert", "shield_check"):
        pts = P((12, 2.8), (19.2, 5.6), (19.2, 12), (12, 21.2), (4.8, 12), (4.8, 5.6), (12, 2.8))
        d.line(pts, fill=c, width=int(w), joint="curve")
        if name == "shield_alert":
            _stroke(d, P((12, 8), (12, 12.6)), w, c)
            d.ellipse(box(10.8, 14.6, 13.2, 17), fill=c)
        elif name == "shield_check":
            _stroke(d, P((8.6, 11.8), (11.2, 14.4), (15.6, 9.2)), w, c)
    elif name == "dice":
        d.rounded_rectangle(box(3.5, 3.5, 20.5, 20.5), radius=4.5 * k, outline=c, width=int(w))
        for x, y in ((8.6, 8.6), (15.4, 8.6), (12, 12), (8.6, 15.4), (15.4, 15.4)):
            d.ellipse(box(x - 1.25, y - 1.25, x + 1.25, y + 1.25), fill=c)
    elif name == "check":
        _stroke(d, P((5, 12.5), (10, 17.5), (19, 7)), w * 1.2, c)
    elif name == "x":
        _stroke(d, P((6, 6), (18, 18)), w, c)
        _stroke(d, P((18, 6), (6, 18)), w, c)
    elif name == "grid":
        for x, y in ((4, 4), (13.5, 4), (4, 13.5), (13.5, 13.5)):
            d.rounded_rectangle(box(x, y, x + 6.5, y + 6.5), radius=2.2 * k, outline=c, width=int(w * 0.85))
    elif name == "arrow":
        _stroke(d, P((4.5, 12), (19.5, 12)), w * 1.1, c)
        _stroke(d, P((13.5, 6), (19.5, 12), (13.5, 18)), w * 1.1, c)
    elif name == "user":
        d.ellipse(box(7.5, 3.5, 16.5, 12.5), outline=c, width=int(w))
        d.arc(box(4, 14, 20, 30), 200, 340, fill=c, width=int(w))
    elif name == "file":
        d.rounded_rectangle(box(5.5, 3, 18.5, 21), radius=3 * k, outline=c, width=int(w))
        _stroke(d, P((9, 9), (15, 9)), w * 0.9, c)
        _stroke(d, P((9, 13), (15, 13)), w * 0.9, c)
    elif name == "clock":
        d.ellipse(box(3.5, 3.5, 20.5, 20.5), outline=c, width=int(w))
        _stroke(d, P((12, 7.5), (12, 12.4), (15.4, 14.4)), w, c)
    elif name == "download":
        _stroke(d, P((12, 4), (12, 15)), w, c)
        _stroke(d, P((7, 10.5), (12, 15.5), (17, 10.5)), w, c)
        _stroke(d, P((5, 20), (19, 20)), w, c)
    elif name == "folder":
        _stroke(d, P((3.5, 8.5), (3.5, 6), (9.5, 6), (11.3, 8), (20.5, 8),
                     (20.5, 19), (3.5, 19), (3.5, 8.5)), w, c)
    elif name == "refresh":
        d.arc(box(4.5, 4.5, 19.5, 19.5), 40, 320, fill=c, width=int(w))
        _stroke(d, P((17.6, 3.6), (18.6, 8.4), (13.8, 8.8)), w, c)
    else:  # unknown -> dot
        d.ellipse(box(9, 9, 15, 15), fill=c)


@lru_cache(maxsize=512)
def icon(name: str, size: int, color: str) -> Image.Image:
    """Vector icon rendered at 8x and reduced. `size` is logical px."""
    px = S(size)
    ss = 8
    big = px * ss
    im = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    _draw_icon(name, d, im, big / 24.0, hex_rgb(color) + (255,))
    return im.resize((px, px), RESAMPLE)


# ---------------------------------------------------------------------- avatars
AVATAR_SPRITES = (
    (("mail", "gmail", "outlook", "yahoo", "proton", "hotmail", "zoho", "inbox"), "tile_mail"),
    (("cloud", "drive", "dropbox", "icloud", "aws", "azure", "onedrive", "mega", "gcp", "hosting", "server"), "tile_cloud"),
    (("bank", "card", "visa", "master", "paypal", "pay", "wallet", "crypto", "binance", "coin", "shop", "amazon", "store"), "tile_card"),
    (("ssh", "key", "vpn", "wifi", "router", "login", "license", "api"), "tile_key"),
    (("security", "shield", "antivirus", "firewall", "2fa", "auth"), "tile_shield"),
    (("web", "forum", "site", "social", "facebook", "twitter", "instagram", "reddit", "browser", "blog"), "tile_globe"),
)
AVATAR_COLORS = (
    ("#74A6FF", "#3C62F0", "#1D2E9E"), ("#FFC77A", "#FF8B2B", "#B54A08"), ("#86F3DE", "#16BFB0", "#066F78"),
    ("#BCA2FF", "#7C55E6", "#40239F"), ("#FFB6F2", "#EE5FD6", "#962088"), ("#FFE690", "#FFC043", "#C47E10"),
    ("#8FB4FF", "#5B6CF2", "#2A2E9E"), ("#9FE88F", "#3DBB5E", "#1B7436"),
)


def avatar_kind(title: str) -> str | None:
    low = title.lower()
    for words, sprite_name in AVATAR_SPRITES:
        if any(w in low for w in words):
            return sprite_name
    return None


def valid_avatar_color(value) -> str:
    """Ignore malformed or missing overrides in old or damaged account data."""
    return value.upper() if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) else ""


def _tint_account_sprite(image: Image.Image, color: str) -> Image.Image:
    """Recolor saturated artwork while retaining neutral details, shading and alpha."""
    rgb = image.convert("RGB")
    saturation = rgb.convert("HSV").getchannel("S")
    mask = saturation.point(lambda s: min(255, max(0, (s - 20) * 5)))
    target = hex_rgb(color)
    shaded = ImageOps.colorize(
        rgb.convert("L"),
        black=tuple(int(c * 0.16) for c in target),
        mid=target,
        white=(255, 255, 255),
        midpoint=150,
    )
    result = Image.composite(shaded, rgb, mask).convert("RGBA")
    result.putalpha(image.getchannel("A"))
    return result


def avatar(title: str, size: int, color: str = "") -> Image.Image:
    """Render an account avatar, using its saved override when it is valid."""
    return _avatar(title, size, valid_avatar_color(color))


@lru_cache(maxsize=512)
def _avatar(title: str, size: int, color: str) -> Image.Image:
    """Clay app-icon tile for an account: a matching sprite or a coloured letter tile."""
    kind = avatar_kind(title)
    px = S(size)
    if kind:
        # Overrides must not inherit the current app theme's sprite tint.
        base = _tint_account_sprite(_base_sprite(kind), color) if color else _sprite_raw(kind)
        # sprites carry 30px padding of the 316px canvas -> crop it so `size` is the tile itself
        pad = int(base.width * 0.138)
        return base.crop((pad, pad, base.width - pad, base.height - pad)).resize((px, px), RESAMPLE)
    digest = int(hashlib.md5(title.strip().lower().encode("utf-8")).hexdigest(), 16)
    if color:
        bottom = hex_rgb(color)
        top = tuple(round(c + (255 - c) * 0.45) for c in bottom)
        dark = tuple(round(c * 0.4) for c in bottom)
    else:
        top, bottom, dark = (hex_rgb(c) for c in AVATAR_COLORS[digest % len(AVATAR_COLORS)])
    n = 256
    mask = new_mask((n, n), lambda dr: dr.rounded_rectangle((4, 4, n - 5, n - 5), radius=78, fill=255))
    tile = clay(mask, top, bottom, dark, softness=0.12, spec=(0.1, 0.04, 0.66, 0.42), spec_strength=0.5)
    letter = (title.strip()[:1] or "?").upper()
    lm = Image.new("L", (n, n), 0)
    f = ImageFont.truetype(str(asset_path("fonts", FONT_FILES["bold"])), 132)
    ImageDraw.Draw(lm).text((n / 2, n / 2 + 6), letter, font=f, fill=255, anchor="mm")
    shadow = Image.new("RGBA", (n, n), dark + (0,))
    shadow.putalpha(lm.point(lambda v: int(v * 0.45)))
    tile = Image.alpha_composite(tile, ImageChops.offset(shadow, 0, 6).filter(ImageFilter.GaussianBlur(5)))
    glyph = clay(lm, (255, 255, 255), (232, 226, 255), (170, 160, 225), softness=0.06, gain=2.6)
    tile = Image.alpha_composite(tile, glyph)
    return tile.resize((px, px), RESAMPLE)


# ------------------------------------------------------------------- text image
@lru_cache(maxsize=256)
def text_image(text: str, size: int, color: str, weight: str = "regular", max_width: int | None = None,
               line_spacing: float = 1.2) -> Image.Image:
    f = pil_font(S(size), weight)
    lines: list[str] = []
    for para in text.split("\n"):
        if max_width is None:
            lines.append(para)
            continue
        cur = ""
        for word in para.split(" "):
            trial = (cur + " " + word).strip()
            if f.getlength(trial) <= S(max_width) or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        lines.append(cur)
    lh = int(S(size) * line_spacing)
    width = max(int(f.getlength(t)) for t in lines) + 4
    img = Image.new("RGBA", (max(width, 4), lh * len(lines) + 6), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((1, i * lh), line, font=f, fill=hex_rgb(color) + (255,))
    return img


def make_ico(path: Path) -> bool:
    try:
        img = Image.open(asset_path("sprites", "app_icon.png")).convert("RGBA")
        img.save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        return True
    except Exception:  # noqa: BLE001
        return False
