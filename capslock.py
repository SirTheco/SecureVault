"""Colours, fonts and small helpers shared by every screen (lavender clay theme).

Every colour is a (light, dark) pair so CustomTkinter widgets switch themes by
themselves.  Our own canvas drawings call pick() to resolve the current mode.
"""
from __future__ import annotations

import customtkinter as ctk

# Palette selected by the user. Values are light/dark pairs; all screens consume these.
_ACTIVE_PALETTE = "Lavender"

# --- surfaces -------------------------------------------------------------
PAGE = ("#DCE3FF", "#13102B")
SIDEBAR_TOP = ("#8D6CF3", "#6C4BDD")
SIDEBAR_BOTTOM = ("#A98CFF", "#8062F0")
CARD = ("#FFFFFF", "#211C4A")
CARD_SOFT = ("#F4F1FF", "#2A2459")
INPUT = ("#F1EEFF", "#2D2761")
BORDER = ("#E4DFFF", "#3B3485")
HOVER = ("#EEEAFF", "#2F2968")
SELECTED = ("#E7E0FF", "#3A3181")

# --- text -------------------------------------------------------------------
TEXT = ("#1C1647", "#F4F2FF")
MUTED = ("#7C77A6", "#A9A4D9")
ON_PRIMARY = "#FFFFFF"

# --- accents ----------------------------------------------------------------
PRIMARY = ("#7B5CF0", "#8F72FF")
PRIMARY_HOVER = ("#6A49E0", "#7E60F0")
PRIMARY_GRAD = ("#A488FF", "#7650EE")
TEAL_GRAD = ("#62EBD2", "#3FBEE6")
PINK_GRAD = ("#FF9BEA", "#E055D8")
ORANGE_GRAD = ("#FFC06A", "#FF8F2E")
BLUE_GRAD = ("#7FA8FF", "#4468F0")
DANGER = ("#E5484D", "#F0686C")
DANGER_HOVER = ("#CC3A3F", "#DB5559")
OK = ("#1FB886", "#38D6A1")
WARN = ("#F2A33A", "#F5B55C")

STRENGTH = ["#E5484D", "#F2803A", "#F2B93A", "#4CC38A", "#1FB886"]

FONT_FAMILY = "Poppins"          # replaced by gfx.init() if it cannot be loaded
FONT_MEDIUM = "Poppins Medium"


def dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def pick(pair) -> str:
    """Resolve a (light, dark) pair (or a plain colour) for the current mode."""
    if isinstance(pair, (tuple, list)):
        return pair[1] if dark() else pair[0]
    return pair


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    family = FONT_MEDIUM if weight == "medium" else FONT_FAMILY
    return ctk.CTkFont(family=family, size=size, weight="bold" if weight == "bold" else "normal")


# Complete colour palettes: page, sidebar top/bottom, card, soft card, input, border,
# hover, selected, text, muted, primary, primary hover, primary gradient, teal gradient.
_PALETTES = {
    "Lavender": {
        "PAGE": ("#E9E7F4", "#171525"), "SIDEBAR_TOP": ("#7965B8", "#40356D"), "SIDEBAR_BOTTOM": ("#9B8AD4", "#51427F"),
        "CARD": ("#FFFFFF", "#242132"), "CARD_SOFT": ("#F5F3FA", "#2D293D"), "INPUT": ("#F0EDF8", "#343047"),
        "BORDER": ("#E1DDED", "#454057"), "HOVER": ("#ECE8F5", "#39344C"), "SELECTED": ("#E4DDF6", "#49405F"),
        "TEXT": ("#28233B", "#F5F2FC"), "MUTED": ("#777187", "#B3ADC4"), "PRIMARY": ("#8067C4", "#B09AF5"),
        "PRIMARY_HOVER": ("#6F55B5", "#9A80E8"), "PRIMARY_GRAD": ("#A99AE0", "#7460B8"), "TEAL_GRAD": ("#A7DED6", "#5B9F9D")},
    "Ocean": {
        "PAGE": ("#E5EFF5", "#101C27"), "SIDEBAR_TOP": ("#397FA0", "#214D68"), "SIDEBAR_BOTTOM": ("#65A8C2", "#2D6A85"),
        "CARD": ("#FFFFFF", "#1B2A38"), "CARD_SOFT": ("#F0F6F9", "#233747"), "INPUT": ("#EAF3F7", "#29404F"),
        "BORDER": ("#D5E5EC", "#385464"), "HOVER": ("#E5F1F6", "#2B4252"), "SELECTED": ("#D6EAF2", "#315365"),
        "TEXT": ("#1B3443", "#F1F8FB"), "MUTED": ("#66808E", "#A5BAC5"), "PRIMARY": ("#337F9F", "#6CC1E0"),
        "PRIMARY_HOVER": ("#286B88", "#4DAACD"), "PRIMARY_GRAD": ("#6FB9D3", "#337F9F"), "TEAL_GRAD": ("#8EDCCB", "#3C9C9A")},
    "Graphite": {
        "PAGE": ("#E8E8EA", "#17181B"), "SIDEBAR_TOP": ("#555960", "#303238"), "SIDEBAR_BOTTOM": ("#777B83", "#41444B"),
        "CARD": ("#FFFFFF", "#24262B"), "CARD_SOFT": ("#F4F4F5", "#2D3036"), "INPUT": ("#EEEEF0", "#373A41"),
        "BORDER": ("#DDDEE1", "#474A52"), "HOVER": ("#E9E9EB", "#383B42"), "SELECTED": ("#DADCE0", "#454952"),
        "TEXT": ("#25272B", "#F5F5F6"), "MUTED": ("#73767D", "#B2B5BC"), "PRIMARY": ("#5B6069", "#B9BEC8"),
        "PRIMARY_HOVER": ("#454951", "#D0D4DB"), "PRIMARY_GRAD": ("#AEB2BA", "#656A74"), "TEAL_GRAD": ("#D0D3D8", "#8B919B")},
    "Rose": {
        "PAGE": ("#F7E9EE", "#291820"), "SIDEBAR_TOP": ("#B66B87", "#6D354B"), "SIDEBAR_BOTTOM": ("#D18DA5", "#8C4760"),
        "CARD": ("#FFFCFD", "#39232D"), "CARD_SOFT": ("#FBEFF3", "#452A36"), "INPUT": ("#F7E7ED", "#52313F"),
        "BORDER": ("#EFD9E1", "#684052"), "HOVER": ("#F7E5EC", "#52313F"), "SELECTED": ("#F1D7E1", "#60384A"),
        "TEXT": ("#482A38", "#FFF2F6"), "MUTED": ("#956C7C", "#D1A7B6"), "PRIMARY": ("#B75F80", "#E39AB4"),
        "PRIMARY_HOVER": ("#9E4D6B", "#CE7F9C"), "PRIMARY_GRAD": ("#E3A5BB", "#B75F80"), "TEAL_GRAD": ("#D6B6D2", "#AD7C9C")},
    "Emerald": {
        "PAGE": ("#E6F1EA", "#14221B"), "SIDEBAR_TOP": ("#3F8867", "#24533F"), "SIDEBAR_BOTTOM": ("#68A987", "#306B50"),
        "CARD": ("#FFFFFF", "#1E3027"), "CARD_SOFT": ("#F0F7F2", "#263D32"), "INPUT": ("#EAF4ED", "#2F493B"),
        "BORDER": ("#D5E8DC", "#3D5B4A"), "HOVER": ("#E4F1E8", "#304A3B"), "SELECTED": ("#D5E9DD", "#365743"),
        "TEXT": ("#1D3B2B", "#F0FAF3"), "MUTED": ("#668675", "#A6C2B1"), "PRIMARY": ("#39835F", "#72C49A"),
        "PRIMARY_HOVER": ("#2D6F50", "#55AE80"), "PRIMARY_GRAD": ("#85C6A3", "#39835F"), "TEAL_GRAD": ("#9CDDC9", "#459B7E")},
    "Sunset": {
        "PAGE": ("#F7EDE2", "#291D18"), "SIDEBAR_TOP": ("#B96F45", "#754127"), "SIDEBAR_BOTTOM": ("#D89461", "#925533"),
        "CARD": ("#FFFCF8", "#3A2921"), "CARD_SOFT": ("#FBF2E8", "#493126"), "INPUT": ("#F6E8D8", "#56392B"),
        "BORDER": ("#EEDCC8", "#694733"), "HOVER": ("#F6E7D7", "#55382A"), "SELECTED": ("#F1DCC5", "#63402D"),
        "TEXT": ("#4B3021", "#FFF5E9"), "MUTED": ("#96765E", "#D2B29A"), "PRIMARY": ("#B66B3D", "#E9A36D"),
        "PRIMARY_HOVER": ("#9E592F", "#D98B52"), "PRIMARY_GRAD": ("#E8B184", "#B66B3D"), "TEAL_GRAD": ("#E8D2A7", "#B68A5A")},
}

def apply_palette(name: str) -> None:
    """Apply a named colour palette without changing the Light/Dark appearance mode."""
    global _ACTIVE_PALETTE
    palette = _PALETTES.get(name, _PALETTES["Lavender"])
    _ACTIVE_PALETTE = name if name in _PALETTES else "Lavender"
    for key, value in palette.items():
        globals()[key] = value

def palette_names() -> tuple[str, ...]:
    return tuple(_PALETTES.keys())
