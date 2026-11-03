"""Soft "clay / inflated 3D" renderer built only on Pillow (no numpy).

Every object is described by a silhouette mask. A blurred copy of the mask is
used as a height field; shifting it towards the light gives diffuse light and
shadow, exactly like an embossed / inflated 3D shape. Used by gen_assets.py to
pre-render the sprites that ship in assets/sprites/.
"""
from __future__ import annotations

from PIL import Image, ImageChops, ImageDraw, ImageFilter

Color = tuple[int, int, int]


def hex_rgb(value: str) -> Color:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _clamp(v: float) -> int:
    return 0 if v < 0 else 255 if v > 255 else int(v)


def new_mask(size, draw_fn, supersample: int = 1) -> Image.Image:
    img = Image.new("L", size, 0)
    d = ImageDraw.Draw(img)
    draw_fn(d)
    return img


def union(*masks: Image.Image) -> Image.Image:
    out = masks[0].copy()
    for m in masks[1:]:
        out = ImageChops.lighter(out, m)
    return out


def subtract(a: Image.Image, b: Image.Image) -> Image.Image:
    return ImageChops.subtract(a, b)


def vertical_gradient(size, top: Color, bottom: Color) -> Image.Image:
    grad = Image.linear_gradient("L").resize(size, Image.Resampling.BILINEAR)
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), grad)


def clay(
    mask: Image.Image,
    top: Color,
    bottom: Color,
    dark: Color,
    light: Color = (255, 255, 255),
    softness: float = 0.10,
    gain: float = 3.2,
    light_strength: float = 0.62,
    shadow_strength: float = 0.78,
    inset: bool = False,
    spec: tuple[float, float, float, float] | None = None,
    spec_strength: float = 0.7,
) -> Image.Image:
    """Return an RGBA image (same size as mask) with a soft 3D look."""
    size = mask.size
    bbox = mask.getbbox() or (0, 0, size[0], size[1])
    span = min(bbox[2] - bbox[0], bbox[3] - bbox[1])
    radius = max(2.0, span * softness)
    height = mask.filter(ImageFilter.GaussianBlur(radius))
    shift = max(1, int(radius * 0.60))
    sign = 1 if inset else -1
    toward_light = ImageChops.offset(height, sign * shift, sign * shift)
    diff = ImageChops.subtract(toward_light, height, 1.0, 128)
    lightmap = diff.point(lambda v: _clamp(128 + (v - 128) * gain))

    base = vertical_gradient(size, top, bottom)
    lit = lightmap.point(lambda v: _clamp((v - 128) * 3.0) * light_strength if v > 128 else 0)
    shd = lightmap.point(lambda v: _clamp((128 - v) * 3.0) * shadow_strength if v < 128 else 0)
    out = Image.composite(Image.new("RGB", size, light), base, lit.point(lambda v: int(v)))
    out = Image.composite(Image.new("RGB", size, dark), out, shd.point(lambda v: int(v)))

    # soft ambient darkening very close to the silhouette edge
    edge = height.point(lambda v: int(max(0, 150 - v) * 0.45))
    out = Image.composite(Image.new("RGB", size, dark), out, edge)

    if spec:
        x0, y0, x1, y1 = (int(spec[0] * size[0]), int(spec[1] * size[1]),
                          int(spec[2] * size[0]), int(spec[3] * size[1]))
        glow = Image.new("L", size, 0)
        ImageDraw.Draw(glow).ellipse((x0, y0, x1, y1), fill=255)
        glow = glow.filter(ImageFilter.GaussianBlur(max(2, (x1 - x0) * 0.28)))
        glow = ImageChops.multiply(glow, mask)
        glow = glow.point(lambda v: int(v * spec_strength))
        out = Image.composite(Image.new("RGB", size, (255, 255, 255)), out, glow)

    rgba = out.convert("RGBA")
    rgba.putalpha(mask)
    return rgba


def drop_shadow(img: Image.Image, offset=(0, 18), blur=22, opacity=0.35, color=(40, 20, 120), pad=70) -> Image.Image:
    w, h = img.size
    canvas = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    alpha = img.getchannel("A")
    sh = Image.new("RGBA", img.size, color + (0,))
    sh.putalpha(alpha.point(lambda v: int(v * opacity)))
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(sh, (pad + offset[0], pad + offset[1]), sh)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas = Image.alpha_composite(canvas, layer)
    canvas.alpha_composite(img, (pad, pad))
    return canvas


def squircle_mask(size, box, radius):
    def fn(d):
        d.rounded_rectangle(box, radius=radius, fill=255)
    return new_mask(size, fn)


def downscale(img: Image.Image, factor: int) -> Image.Image:
    if factor == 1:
        return img
    return img.resize((img.width // factor, img.height // factor), Image.Resampling.LANCZOS)
