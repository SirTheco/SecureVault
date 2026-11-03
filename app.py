"""Rebuild the hero illustration sprites with Pillow. Run from any directory."""
from pathlib import Path
from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parents[1] / "assets" / "sprites"
SS = 3


def rgba(hex_color, alpha=255):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (alpha,)


def mask(size, painter):
    image = Image.new("L", tuple(v * SS for v in size), 0)
    painter(ImageDraw.Draw(image))
    return image


def gradient(size, a, b):
    w, h = (v * SS for v in size)
    top, bottom = rgba(a), rgba(b)
    ramp = Image.new("RGBA", (1, h))
    ramp.putdata([tuple(round(top[i] + (bottom[i] - top[i]) * y / max(1, h - 1))
                        for i in range(4)) for y in range(h)])
    return ramp.resize((w, h))


def layer(canvas, m, a, b=None):
    fill = gradient((canvas.width // SS, canvas.height // SS), a, b or a)
    fill.putalpha(m)
    canvas.alpha_composite(fill)


def shadow(canvas, m, color="#14214d", offset=8, blur=10, opacity=85):
    alpha = m.filter(ImageFilter.GaussianBlur(blur * SS)).point(lambda p: p * opacity // 255)
    alpha = ImageChops.offset(alpha, 0, offset * SS)
    shade = Image.new("RGBA", canvas.size, rgba(color, 0))
    shade.putalpha(alpha)
    canvas.alpha_composite(shade)


def line(draw, points, color, width=7):
    points = [(round(x * SS), round(y * SS)) for x, y in points]
    w = width * SS
    draw.line(points, fill=rgba(color), width=w, joint="curve")
    r = w / 2
    for x, y in (points[0], points[-1]):
        draw.ellipse((int(x-r), int(y-r), int(x+r), int(y+r)), fill=rgba(color))


def rect(box):
    return tuple(round(n * SS) for n in box)


def save(image, name):
    image.resize((image.width // SS, image.height // SS), Image.Resampling.LANCZOS).save(
        OUT / (name + ".png"), optimize=True)


def tile(name, top, bottom, symbol):
    size = (316, 316)
    image = Image.new("RGBA", (316 * SS, 316 * SS))
    shape = mask(size, lambda d: d.rounded_rectangle(rect((30, 30, 286, 286)), radius=66 * SS, fill=255))
    shadow(image, shape, offset=9, blur=12, opacity=85)
    layer(image, shape, top, bottom)
    d = ImageDraw.Draw(image)
    # A small highlight and inset hairline give all tiles one family resemblance.
    d.rounded_rectangle(rect((34, 34, 282, 282)), radius=62 * SS,
                        outline=rgba("#ffffff", 80), width=2 * SS)
    d.arc(rect((52, 46, 264, 185)), 195, 320, fill=rgba("#ffffff", 60), width=3 * SS)
    white = "#f8faff"
    if symbol == "cloud":
        d.rounded_rectangle(rect((85, 140, 231, 206)), radius=33 * SS, fill=rgba(white))
        d.ellipse(rect((111, 99, 200, 188)), fill=rgba(white))
        d.ellipse(rect((164, 125, 224, 185)), fill=rgba(white))
        line(d, [(105, 220), (211, 220)], "#c7ddff", 3)
    elif symbol == "shield":
        d.polygon([tuple(v * SS for v in p) for p in ((158, 73), (226, 98), (226, 157), (214, 194),
                  (190, 218), (158, 235), (126, 218), (102, 194), (90, 157), (90, 98))], fill=rgba(white))
        line(d, [(126, 157), (149, 178), (193, 132)], "#187f83", 9)
    elif symbol == "key":
        d.ellipse(rect((79, 105, 159, 185)), outline=rgba(white), width=11 * SS)
        line(d, [(148, 145), (233, 145), (233, 168)], white, 11)
        line(d, [(208, 145), (208, 163)], white, 10)
    elif symbol == "card":
        d.rounded_rectangle(rect((90, 91, 226, 231)), radius=22 * SS, fill=rgba(white))
        d.rounded_rectangle(rect((129, 80, 187, 106)), radius=12 * SS, fill=rgba("#dcd2ff"))
        line(d, [(122, 160), (148, 184), (194, 133)], "#7650d6", 9)
    elif symbol == "mail":
        d.rounded_rectangle(rect((77, 105, 239, 212)), radius=20 * SS, fill=rgba(white))
        line(d, [(88, 120), (158, 168), (228, 120)], "#c0469f", 7)
        line(d, [(90, 197), (122, 173)], "#e7b4da", 4)
        line(d, [(226, 197), (194, 173)], "#e7b4da", 4)
    elif symbol == "user":
        d.ellipse(rect((125, 92, 191, 158)), fill=rgba(white))
        d.rounded_rectangle(rect((95, 171, 221, 222)), radius=25 * SS, fill=rgba(white))
        d.ellipse(rect((113, 151, 203, 225)), fill=rgba(white))
        d.rectangle(rect((95, 205, 221, 222)), fill=rgba(white))
    elif symbol == "globe":
        d.ellipse(rect((93, 93, 223, 223)), outline=rgba(white), width=8 * SS)
        d.ellipse(rect((130, 93, 186, 223)), outline=rgba(white), width=6 * SS)
        line(d, [(95, 158), (221, 158)], white, 6)
        line(d, [(106, 128), (210, 128)], white, 4)
        line(d, [(106, 188), (210, 188)], white, 4)
    save(image, name)


def padlock():
    size = (390, 450)
    body = Image.new("RGBA", (390 * SS, 450 * SS))
    shackle = Image.new("RGBA", body.size)
    sh = mask(size, lambda d: (
        d.rounded_rectangle(rect((91, 48, 299, 300)), radius=104 * SS, fill=255),
        d.rounded_rectangle(rect((140, 98, 250, 318)), radius=55 * SS, fill=0)))
    shadow(shackle, sh, "#1d2c59", 7, 10, 90)
    # polished silver shackle: bright top, cool grey base, specular arc and a darker reflected edge
    layer(shackle, sh, "#ffffff", "#7f8ba6")
    d = ImageDraw.Draw(shackle)
    d.arc(rect((106, 63, 284, 236)), 190, 340, fill=rgba("#ffffff", 220), width=5 * SS)
    d.arc(rect((112, 70, 278, 230)), 200, 250, fill=rgba("#5d6880", 120), width=3 * SS)
    # specular stripes down both legs, like polished chrome
    for x0 in (100, 262):
        d.rounded_rectangle(rect((x0, 120, x0 + 10, 210)), radius=5 * SS, fill=rgba("#ffffff", 190))
    # gold collar caps where the shackle enters the body
    collar = mask(size, lambda d: (
        d.rounded_rectangle(rect((80, 132, 152, 186)), radius=14 * SS, fill=255),
        d.rounded_rectangle(rect((238, 132, 310, 186)), radius=14 * SS, fill=255)))
    shadow(shackle, collar, "#3a2a00", 4, 6, 70)
    layer(shackle, collar, "#fff1b0", "#b7791f")
    d = ImageDraw.Draw(shackle)
    line(d, [(94, 142), (94, 178)], "#ffffff", 3)
    line(d, [(256, 142), (256, 178)], "#ffffff", 3)
    shape = mask(size, lambda d: d.rounded_rectangle(rect((43, 171, 347, 411)), radius=61 * SS, fill=255))
    shadow(body, shape, "#17245c", 10, 13, 105)
    # glossy 3D body: light-to-deep blue gradient (tinted to the palette at runtime)
    layer(body, shape, "#9dbcff", "#2a4fc0")
    gloss = mask(size, lambda d: d.rounded_rectangle(rect((58, 182, 332, 252)), radius=34 * SS, fill=255))
    gl = Image.new("RGBA", body.size, (255, 255, 255, 0))
    gl.putalpha(gloss.point(lambda v: v * 95 // 255))
    body.alpha_composite(gl)
    d = ImageDraw.Draw(body)
    d.rounded_rectangle(rect((48, 176, 342, 406)), radius=56 * SS, outline=rgba("#ffffff", 85), width=2 * SS)
    # white keyhole with a soft recess shadow underneath
    keyhole = ((180, 282), (210, 282), (221, 351), (169, 351))
    d.ellipse(rect((169, 249, 221, 301)), fill=rgba("#10206a", 110))
    d.polygon([tuple(v * SS for v in (x, y + 4)) for x, y in keyhole], fill=rgba("#10206a", 110))
    d.ellipse(rect((169, 245, 221, 297)), fill=rgba("#ffffff"))
    d.polygon([tuple(v * SS for v in p) for p in keyhole], fill=rgba("#ffffff"))
    save(body, "padlock_body")
    save(shackle, "padlock_shackle")


def cloud():
    size = (380, 260)
    im = Image.new("RGBA", (380 * SS, 260 * SS))
    m = mask(size, lambda d: (
        d.rounded_rectangle(rect((40, 130, 340, 215)), radius=43 * SS, fill=255),
        d.ellipse(rect((70, 98, 190, 210)), fill=255),
        d.ellipse(rect((135, 52, 260, 188)), fill=255),
        d.ellipse(rect((220, 100, 320, 200)), fill=255)))
    shadow(im, m, "#253670", 6, 13, 45)
    layer(im, m, "#ffffff", "#cdd9f7")
    # soft glossy highlight along the top of the puffs
    gloss = Image.new("RGBA", im.size, (255, 255, 255, 0))
    ImageDraw.Draw(gloss).ellipse(rect((110, 66, 250, 120)), fill=rgba("#ffffff", 150))
    gloss = gloss.filter(ImageFilter.GaussianBlur(4 * SS))
    gloss.putalpha(ImageChops.multiply(gloss.getchannel("A"), m))
    im.alpha_composite(gloss)
    save(im, "cloud")


def orb(name, top, bottom):
    size = (220, 220)
    im = Image.new("RGBA", (220 * SS, 220 * SS))
    m = mask(size, lambda d: d.ellipse(rect((20, 20, 200, 200)), fill=255))
    shadow(im, m, "#202856", 5, 8, 60)
    layer(im, m, top, bottom)
    d = ImageDraw.Draw(im)
    d.ellipse(rect((48, 42, 100, 76)), fill=rgba("#ffffff", 115))
    save(im, name)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for args in (
        ("tile_cloud", "#6da5ff", "#3155c9", "cloud"),
        ("tile_shield", "#69ddcf", "#168e91", "shield"),
        ("tile_key", "#ffbb75", "#d97a31", "key"),
        ("tile_card", "#b4a2ff", "#7050ca", "card"),
        ("tile_mail", "#f49bd7", "#bf4da3", "mail"),
        ("tile_user", "#ffd978", "#e39a2b", "user"),
        ("tile_globe", "#6dcce5", "#3689ad", "globe"),
    ):
        tile(*args)
    # padlock_body / padlock_shackle are now cut from a 3D render (assets/sprites_hires/padlock_3d_source.png)
    cloud()
    orb("orb_pink", "#ffb5e3", "#c056b6")
    orb("orb_teal", "#86ece0", "#169c9c")
    orb("orb_orange", "#ffda9b", "#df883d")
