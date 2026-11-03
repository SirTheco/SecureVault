"""A small, focus-aware Caps Lock hint for text inputs."""
from __future__ import annotations

import ctypes
import sys
import tkinter as tk

import customtkinter as ctk

from . import theme


def _windows_caps_lock():
    if sys.platform != "win32":
        return None
    try:
        return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
    except (AttributeError, OSError):
        return None


def attach_caps_hint(widget, parent, row, column=0, **grid_options):
    """Place a hint below an input; it exists only while focused and Caps is on."""
    hint = ctk.CTkLabel(parent, text="Caps Lock is on", text_color=theme.WARN,
                        font=theme.font(11), height=18, anchor="w")
    hint.grid(row=row, column=column, sticky="w", **grid_options)
    hint.grid_remove()
    native = getattr(widget, "_entry", getattr(widget, "_textbox", widget))
    state = {"focused": False, "caps": False, "visible": False, "job": None}

    def refresh():
        if state["job"] is not None:
            try:
                native.after_cancel(state["job"])
            except tk.TclError:
                pass
        state["job"] = None
        if not state["focused"]:
            return
        actual = _windows_caps_lock()
        if actual is not None:
            state["caps"] = actual
        visible = state["caps"]
        if visible != state["visible"]:
            (hint.grid if visible else hint.grid_remove)()
            state["visible"] = visible
        if actual is not None:
            state["job"] = native.after(150, refresh)

    def focus_in(_event):
        state["focused"] = True
        refresh()

    def focus_out(_event):
        state["focused"] = False
        if state["job"] is not None:
            try:
                native.after_cancel(state["job"])
            except tk.TclError:
                pass
            state["job"] = None
        if state["visible"]:
            hint.grid_remove()
            state["visible"] = False

    def key(event):
        if sys.platform != "win32":
            # Tk/X11 LockMask is the state before a key press.
            state["caps"] = bool(event.state & 0x02)
            if event.keysym == "Caps_Lock" and event.type == tk.EventType.KeyPress:
                state["caps"] = not state["caps"]
        refresh()

    native.bind("<FocusIn>", focus_in, add="+")
    native.bind("<FocusOut>", focus_out, add="+")
    native.bind("<KeyPress>", key, add="+")
    return hint
