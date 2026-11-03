"""Pre-renders the soft 3D "clay" sprites used by SecureVault's interface.

Run from the project root:   python tools/gen_assets.py
Output: assets/sprites/*.png   (these files ship with the app; this script is
only needed if you want to change the artwork).  Needs only Pillow.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from vault.ui.clay import (clay, downscale, drop_shadow, hex_rgb as C, new_mask,  # noqa: E402
                  squircle_mask, subtract, union)

OUT = Path(__file__).resolve().parent.parent / "assets" / "sprites"
OUT.mkdir(parents=True, exist_ok=True)
SS = 2                      # files are written at half of the render size

# colour sets: (top, bottom, dark)
BLUE = (C("#74A6FF"), C("#3C62F0"), C("#1D2E9E"))
ORANGE = (C("#FFC77A"), C("#FF8B2B"), C("#B54A08"))
TEAL = (C("#86F3DE"), C("#16BFB0"), C("#066F78"))
PURPLE = (C("#BCA2FF"), C("#7C55E6"), C("#40239F"))
PINK = (C("#FFB6F2"), C("#EE5FD6"), C("#962088"))
YELLOW = (C("#FFE690"), C("#FFC043"), C("#C47E10"))
WHITE = (C("#FFFFFF"), C("#E6E1FF"), C("#9E96DC"))
SILVER = (C("#FBFAFF"), C("#BDB7EC"), C("#7D75C2"))
NAVY = (C("#4A3F9A"), C("#1F1760"), C("#0B0733"))
SKIN = (C("#FFCB9C"), C("#F0A06A"), C("#B5603A"))
BROWN = (C("#7A5238"), C("#4A2D1C"), C("#22110A"))
GOLD = (C("#FFE9A0"), C("#F5B93A"), C("#A8680A"))


def save(img: Image.Image, name: str) -> None:
    downscale(img, SS).save(OUT / f"{name}.png", optimize=True)
    print("wrote", name)


# ---------------------------------------------------------------- glyph masks
N = 512


def glyph_cloud():
    def fn(d):
        d.ellipse((96, 250, 232, 386), fill=255)
        d.ellipse((160, 150, 352, 342), fill=255)
        d.ellipse((290, 230, 420, 360), fill=255)
        d.rounded_rectangle((120, 280, 396, 388), radius=54, fill=255)
    return new_mask((N, N), fn)


def glyph_key():
    ring = new_mask((N, N), lambda d: d.ellipse((92, 160, 252, 320), fill=255))
    hole = new_mask((N, N), lambda d: d.ellipse((140, 208, 204, 272), fill=255))
    shaft = new_mask((N, N), lambda d: d.rounded_rectangle((226, 218, 420, 262), radius=22, fill=255))
    t1 = new_mask((N, N), lambda d: d.rounded_rectangle((330, 250, 364, 322), radius=14, fill=255))
    t2 = new_mask((N, N), lambda d: d.rounded_rectangle((384, 250, 416, 304), radius=14, fill=255))
    return subtract(union(ring, shaft, t1, t2), hole)


def _check(d, pts, width):
    d.line(pts, fill=255, width=width, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x - width // 2, y - width // 2, x + width // 2, y + width // 2), fill=255)


def glyph_shield():
    def fn(d):
        d.polygon([(256, 108), (392, 158), (392, 262), (256, 410), (120, 262), (120, 158)], fill=255)
        d.ellipse((120, 168, 392, 440), fill=255)
        d.polygon([(120, 158), (392, 158), (392, 300), (120, 300)], fill=255)
        d.polygon([(256, 108), (392, 158), (120, 158)], fill=255)
    base = new_mask((N, N), fn)
    # tidy: round the whole silhouette a little
    base = base.filter(ImageFilter.GaussianBlur(7)).point(lambda v: 255 if v > 128 else 0).filter(ImageFilter.GaussianBlur(1.2))
    chk = new_mask((N, N), lambda d: _check(d, [(190, 268), (240, 316), (330, 214)], 34))
    return subtract(base, chk)


def glyph_mail():
    body = new_mask((N, N), lambda d: d.rounded_rectangle((100, 150, 412, 362), radius=36, fill=255))
    flap = new_mask((N, N), lambda d: d.line([(120, 178), (256, 282), (392, 178)], fill=255, width=22, joint="curve"))
    return subtract(body, flap)


def glyph_clipboard():
    board = new_mask((N, N), lambda d: d.rounded_rectangle((136, 118, 376, 404), radius=44, fill=255))
    clip = new_mask((N, N), lambda d: d.rounded_rectangle((200, 84, 312, 150), radius=30, fill=255))
    chk = new_mask((N, N), lambda d: _check(d, [(196, 270), (246, 320), (324, 226)], 32))
    return subtract(union(board, clip), chk)


def glyph_globe():
    ball = new_mask((N, N), lambda d: d.ellipse((116, 116, 396, 396), fill=255))

    def lines(d):
        d.ellipse((190, 116, 322, 396), outline=255, width=14)
        d.line([(116, 256), (396, 256)], fill=255, width=14)
        d.arc((116, 170, 396, 342), 0, 180, fill=255, width=12)
        d.arc((116, 170, 396, 342), 180, 360, fill=255, width=12)
        d.line([(256, 116), (256, 396)], fill=255, width=14)
    return subtract(ball, new_mask((N, N), lines))


def tile(bg, glyph_mask=None, name="tile", glyph_colors=WHITE, extra_layers=None):
    """A rounded app-icon tile with a raised white glyph."""
    m = squircle_mask((N, N), (30, 30, 482, 482), 150)
    t = clay(m, *bg, softness=0.115, spec=(0.12, 0.06, 0.62, 0.40), spec_strength=0.55)
    if glyph_mask is not None:
        shadow = Image.new("RGBA", (N, N), bg[2] + (0,))
        shadow.putalpha(glyph_mask.point(lambda v: int(v * 0.45)))
        shadow = ImageChops.offset(shadow, 0, 12).filter(ImageFilter.GaussianBlur(10))
        t = Image.alpha_composite(t, shadow)
        g = clay(glyph_mask, *glyph_colors, softness=0.07, gain=3.0, spec=(0.1, 0.05, 0.6, 0.45), spec_strength=0.5)
        t = Image.alpha_composite(t, g)
    if extra_layers:
        for layer in extra_layers:
            t = Image.alpha_composite(t, layer)
    out = drop_shadow(t, offset=(0, 22), blur=22, opacity=0.40, color=bg[2], pad=60)
    save(out, name)
    return out


def face_layers():
    layers = []
    head = new_mask((N, N), lambda d: d.ellipse((136, 150, 376, 404), fill=255))
    layers.append(clay(head, *SKIN, softness=0.16, spec=(0.18, 0.2, 0.5, 0.5), spec_strength=0.5))
    hair = new_mask((N, N), lambda d: (d.ellipse((126, 120, 386, 330), fill=255)))
    cut = new_mask((N, N), lambda d: d.ellipse((150, 190, 362, 420), fill=255))
    hair = subtract(hair, cut)
    hair = union(hair, new_mask((N, N), lambda d: d.ellipse((150, 118, 362, 230), fill=255)))
    hair = subtract(hair, new_mask((N, N), lambda d: d.ellipse((168, 190, 344, 300), fill=255)))
    layers.append(clay(hair, *BROWN, softness=0.12))
    beard = new_mask((N, N), lambda d: d.ellipse((150, 280, 362, 430), fill=255))
    beard = subtract(beard, new_mask((N, N), lambda d: d.ellipse((196, 270, 316, 350), fill=255)))
    beard = subtract(beard, new_mask((N, N), lambda d: d.rectangle((120, 140, 400, 290), fill=255)))
    layers.append(clay(beard, *BROWN, softness=0.14))
    for cx in (212, 300):
        eye = new_mask((N, N), lambda d, cx=cx: d.ellipse((cx - 17, 238, cx + 17, 288), fill=255))
        layers.append(clay(eye, C("#4B3B6E"), C("#1A1130"), C("#0B0620"), softness=0.3))
    mouth = new_mask((N, N), lambda d: d.arc((206, 318, 306, 372), 20, 160, fill=255, width=14))
    layers.append(clay(mouth, C("#E8736A"), C("#B83A3A"), C("#6B1717"), softness=0.3))
    return layers


# --------------------------------------------------------------------- padlock
PW, PH = 640, 760


def padlock_parts():
    body_m = new_mask((PW, PH), lambda d: d.rounded_rectangle((70, 300, 570, 700), radius=110, fill=255))
    keyhole = new_mask((PW, PH), lambda d: (d.ellipse((268, 420, 372, 524), fill=255),
                                            d.polygon([(292, 500), (348, 500), (366, 618), (274, 618)], fill=255),
                                            d.rounded_rectangle((292, 560, 348, 618), radius=14, fill=255)))
    body_m_cut = subtract(body_m, keyhole)

    shackle_m = new_mask((PW, PH), lambda d: (
        d.rounded_rectangle((148, 46, 492, 470), radius=172, fill=255),
        d.rounded_rectangle((232, 130, 408, 520), radius=88, fill=0)))
    body = clay(body_m_cut, *BLUE, softness=0.095, gain=3.4, spec=(0.1, 0.38, 0.55, 0.60), spec_strength=0.5)
    # engraved dark keyhole
    key = clay(keyhole, *NAVY, softness=0.2, inset=True, light_strength=0.18)
    body = Image.alpha_composite(body, key)
    # glossy band below the shackle
    band = new_mask((PW, PH), lambda d: d.rounded_rectangle((100, 330, 540, 368), radius=19, fill=255))
    band = ImageChops.multiply(band, body_m_cut)
    band_i = Image.new("RGBA", (PW, PH), (255, 255, 255, 0))
    band_i.putalpha(band.point(lambda v: int(v * 0.22)))
    body = Image.alpha_composite(body, band_i)
    shackle = clay(shackle_m, *SILVER, softness=0.13, gain=3.2, spec=(0.18, 0.04, 0.48, 0.3), spec_strength=0.6)
    return body, shackle


# ------------------------------------------------------------------- scenery
def cloud_sprite(name="cloud", w=640, h=400):
    def fn(d):
        d.ellipse((60, 150, 260, 350), fill=255)
        d.ellipse((170, 50, 430, 310), fill=255)
        d.ellipse((330, 120, 560, 350), fill=255)
        d.rounded_rectangle((90, 210, 540, 350), radius=70, fill=255)
    m = new_mask((w, h), fn)
    c = clay(m, C("#FFFFFF"), C("#E9E5FF"), C("#A99FE6"), softness=0.16, gain=2.8, spec=(0.25, 0.1, 0.6, 0.5), spec_strength=0.4)
    save(drop_shadow(c, offset=(0, 24), blur=26, opacity=0.28, color=C("#4B33B8"), pad=60), name)


def orb(name, colors, d=360, spec=True):
    m = new_mask((d, d), lambda dr: dr.ellipse((8, 8, d - 8, d - 8), fill=255))
    c = clay(m, *colors, softness=0.30, gain=2.6, spec=(0.18, 0.1, 0.52, 0.45) if spec else None, spec_strength=0.55)
    save(drop_shadow(c, offset=(0, 16), blur=16, opacity=0.35, color=colors[2], pad=40), name)


def app_icon():
    size = 1024
    m = squircle_mask((size, size), (40, 40, size - 40, size - 40), 230)
    bg = clay(m, C("#A98BFF"), C("#6A47E0"), C("#3A1FA0"), softness=0.10, spec=(0.1, 0.05, 0.7, 0.4), spec_strength=0.45)
    body_m = new_mask((size, size), lambda d: d.rounded_rectangle((272, 470, 752, 830), radius=100, fill=255))
    shackle_m = new_mask((size, size), lambda d: (
        d.rounded_rectangle((344, 190, 680, 640), radius=168, fill=255),
        d.rounded_rectangle((426, 272, 598, 700), radius=86, fill=0)))
    hole = new_mask((size, size), lambda d: (d.ellipse((462, 580, 562, 680), fill=255),
                                             d.polygon([(486, 660), (538, 660), (552, 750), (472, 750)], fill=255)))
    sh = clay(shackle_m, *WHITE, softness=0.13)
    body = clay(subtract(body_m, hole), *WHITE, softness=0.09, spec=(0.1, 0.45, 0.55, 0.65), spec_strength=0.5)
    key = clay(hole, *PURPLE, softness=0.22, inset=True, light_strength=0.2)
    img = bg
    for layer in (sh, body, key):
        shadow = Image.new("RGBA", (size, size), (40, 20, 120, 0))
        shadow.putalpha(layer.getchannel("A").point(lambda v: int(v * 0.35)))
        shadow = ImageChops.offset(shadow, 0, 16).filter(ImageFilter.GaussianBlur(14))
        img = Image.alpha_composite(img, shadow)
        img = Image.alpha_composite(img, layer)
    img = img.resize((512, 512), Image.Resampling.LANCZOS)
    img.save(OUT / "app_icon.png", optimize=True)
    print("wrote app_icon")


def main() -> None:
    tile(BLUE, glyph_cloud(), "tile_cloud")
    tile(ORANGE, glyph_key(), "tile_key")
    tile(TEAL, glyph_shield(), "tile_shield")
    tile(PURPLE, glyph_clipboard(), "tile_card")
    tile(PINK, glyph_mail(), "tile_mail")
    tile((C("#8FB4FF"), C("#5B6CF2"), C("#2A2E9E")), glyph_globe(), "tile_globe")
    tile(YELLOW, None, "tile_user", extra_layers=face_layers())

    body, shackle = padlock_parts()
    save(drop_shadow(body, offset=(0, 26), blur=26, opacity=0.38, color=C("#241580"), pad=70), "padlock_body")
    save(drop_shadow(shackle, offset=(0, 18), blur=18, opacity=0.34, color=C("#241580"), pad=70), "padlock_shackle")

    cloud_sprite("cloud")
    orb("orb_teal", TEAL)
    orb("orb_pink", PINK)
    orb("orb_orange", ORANGE)
    orb("orb_blue", BLUE)
    app_icon()


if __name__ == "__main__":
    main()
