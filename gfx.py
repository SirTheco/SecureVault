"""Settings screen (shown in the detail panel)."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

import os
import sys
import time

from ..backup import list_backups, make_backup
from ..utils import fmt_ts, open_path
from . import anim, theme
from .gfx import S
from .dialogs import ChangePasswordDialog, RecoveryKeyDialog
from .widgets import Chip, GButton


class _Toggle(tk.Canvas):
    """On/off switch whose knob and track glide between states (respects the Animations setting)."""

    def __init__(self, parent, var, command):
        super().__init__(parent, width=S(52), height=S(30), bg=theme.pick(theme.CARD_SOFT), highlightthickness=0,
                         bd=0, cursor="hand2")
        self.var, self.command = var, command
        self._pos = 1.0 if var.get() else 0.0
        self._key = ("toggle", id(self))
        self._photo = None
        self._image_id = self.create_image(0, 0, anchor="nw")
        self.bind("<Button-1>", self._click)
        self._draw()

    def _draw(self) -> None:
        w, h, pad = S(52), S(30), S(3)
        r = (h - 2 * pad) / 2
        track = anim.lerp_hex(theme.pick(theme.BORDER), theme.pick(theme.PRIMARY), self._pos)
        # Render at four times the target size, then downsample for smooth edges.
        ss = 4
        image = Image.new("RGB", (w * ss, h * ss), theme.pick(theme.CARD_SOFT))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=h * ss / 2, fill=track)
        cx = pad + r + self._pos * (w - 2 * (pad + r))
        cy = h / 2
        draw.ellipse(((cx - r) * ss, (cy - r) * ss, (cx + r) * ss - 1, (cy + r) * ss - 1),
                     fill="#FFFFFF")
        image = image.resize((w, h), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(image, master=self)
        self.itemconfigure(self._image_id, image=self._photo)

    def _click(self, _event=None) -> None:
        new = not bool(self.var.get())
        self.var.set(new)
        start, target = self._pos, 1.0 if new else 0.0

        def step(t: float) -> None:
            self._pos = start + (target - start) * t
            self._draw()
        anim.start(self._key, 240, step, ease=anim.ease_in_out)
        if self.command:
            self.command()


def _switch(parent, var, command):
    return _Toggle(parent, var, command)


def _menu(parent, values, current, command, width=150):
    m = ctk.CTkOptionMenu(parent, values=values, width=width, height=36, corner_radius=12, command=command,
                          fg_color=theme.INPUT, button_color=theme.PRIMARY, button_hover_color=theme.PRIMARY_HOVER,
                          text_color=theme.TEXT, dropdown_fg_color=theme.CARD, dropdown_text_color=theme.TEXT,
                          dropdown_hover_color=theme.HOVER, font=theme.font(12), dropdown_font=theme.font(12))
    m.set(current)
    return m


class SettingsPanel(anim.SmoothScrollFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent", scrollbar_button_color=theme.BORDER,
                         scrollbar_button_hover_color=theme.PRIMARY)
        self.app, self.settings, self.db = app, app.settings, app.db
        self.columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text="Settings", font=theme.font(26, "bold"), text_color=theme.TEXT, anchor="w").grid(
            row=0, column=0, sticky="ew", padx=20, pady=(18, 0))
        ctk.CTkLabel(self, text="Make SecureVault look and behave the way you like.", font=theme.font(12),
                     text_color=theme.MUTED, anchor="w").grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 6))
        self._r = 2

        card = self._card("Appearance")
        seg = ctk.CTkFrame(card, fg_color="transparent")
        self._chips = []
        for i, name in enumerate(("System", "Light", "Dark")):
            chip = Chip(seg, name, lambda n=name: self._pick_theme(n), selected=name == self.settings.get("theme"),
                        grad=theme.PRIMARY_GRAD, bg=theme.CARD_SOFT, height=34, size=12)
            chip.pack(side="left", padx=3)
            self._chips.append((name, chip))
        self._row(card, "Appearance", "Light, dark, or follow your system", seg)
        palette_seg = ctk.CTkFrame(card, fg_color="transparent")
        self._palette_chips = []
        for name in theme.palette_names():
            chip = Chip(palette_seg, name, lambda n=name: self._pick_palette(n),
                        selected=name == self.settings.get("palette"), grad=theme.PRIMARY_GRAD,
                        bg=theme.CARD_SOFT, height=32, size=11)
            chip.pack(side="left", padx=3, pady=2)
            self._palette_chips.append((name, chip))
        self._row(card, "Color theme", "Choose an accent and surface palette", palette_seg)
        self.anim = tk.BooleanVar(value=bool(self.settings.get("animations")))
        self._row(card, "Animations", "Gentle icon motion, transitions and the opening padlock",
                  _switch(card, self.anim, lambda: self.settings.set("animations", bool(self.anim.get()))))
        self.icon_motion = tk.BooleanVar(value=bool(self.settings.get("icon_motion")))
        self._row(card, "Icon hover & click", "Icons lift and wobble under the pointer and bounce when clicked",
                  _switch(card, self.icon_motion, lambda: self.settings.set("icon_motion", bool(self.icon_motion.get()))))

        card = self._card("Security")
        self._row(card, "Auto-lock", "Lock after this many minutes without activity", _menu(
            card, ["1", "2", "5", "10", "15", "30", "60"], str(self.settings.get("autolock_minutes")),
            lambda v: self.settings.set("autolock_minutes", int(v)), 100))
        self.lock_min = tk.BooleanVar(value=bool(self.settings.get("lock_on_minimize")))
        self._row(card, "Lock when minimized", "Lock the vault as soon as the window is minimized",
                  _switch(card, self.lock_min, lambda: self.settings.set("lock_on_minimize", bool(self.lock_min.get()))))
        self.lock_close = tk.BooleanVar(value=bool(self.settings.get("lock_on_close")))
        self._row(card, "Lock when closed to tray", "Closing the window keeps the app in the tray, locked",
                  _switch(card, self.lock_close, lambda: self.settings.set("lock_on_close", bool(self.lock_close.get()))))
        clip = self.settings.get("clipboard_clear_seconds")
        self._row(card, "Clear copied passwords", "Wipe the clipboard after copying a password", _menu(
            card, ["Never", "10 s", "20 s", "30 s", "60 s", "120 s"], "Never" if not clip else f"{clip} s",
            self._clip, 100))
        self._row(card, "Master password", "Change the password that unlocks your vault",
                  GButton(card, "Change…", lambda: ChangePasswordDialog(self.winfo_toplevel(), self.db), width=130,
                          height=38, style="soft", size=12, bg=theme.CARD_SOFT))
        self._row(card, "Recovery key", "Creating a new key makes the old one stop working",
                  GButton(card, "Generate new…", self._new_recovery, width=140, height=38, style="soft", size=12,
                          bg=theme.CARD_SOFT))

        card = self._card("Backups")
        self.auto_var = tk.BooleanVar(value=bool(self.settings.get("auto_backup")))
        self._row(card, "Automatic backups", "Encrypted copy of your vault, at most every 12 hours",
                  _switch(card, self.auto_var, lambda: self.settings.set("auto_backup", bool(self.auto_var.get()))))
        self._row(card, "Backups to keep", "Older ones are deleted automatically", _menu(
            card, ["3", "5", "10", "20", "50"], str(self.settings.get("backups_to_keep")),
            lambda v: self.settings.set("backups_to_keep", int(v)), 100))
        self.backup_info = ctk.CTkLabel(card, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w")
        self.backup_info.grid(row=card._n, column=0, columnspan=2, sticky="ew", padx=20, pady=(2, 0))
        card._n += 1
        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.grid(row=card._n, column=0, columnspan=2, sticky="w", padx=16, pady=(8, 16))
        for text, cmd, icon, w in (("Back up now", self._backup_now, "download", 150),
                                   ("Open folder", self._open_folder, "folder", 140),
                                   ("Restore…", self._restore, "refresh", 130)):
            GButton(btns, text, cmd, width=w, height=38, style="soft", icon=icon, size=12, bg=theme.CARD_SOFT).pack(
                side="left", padx=(4, 6))
        self._refresh_backup_info()

        card = self._card("About")
        from .. import __version__
        ctk.CTkLabel(card, text=f"SecureVault {__version__}\nData folder:  {app.data_dir}", font=theme.font(12),
                     text_color=theme.MUTED, anchor="w", justify="left", wraplength=560).grid(
            row=card._n, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 8))
        card._n += 1
        GButton(card, "Open data folder", lambda: open_path(app.data_dir), width=170, height=38, style="soft", size=12,
                icon="folder", bg=theme.CARD_SOFT).grid(row=card._n, column=0, sticky="w", padx=16, pady=(0, 16))

    # -------------------------------------------------------------- layout
    def _card(self, title: str):
        card = ctk.CTkFrame(self, fg_color=theme.CARD_SOFT, corner_radius=26)
        card.grid(row=self._r, column=0, sticky="ew", padx=14, pady=(14, 0))
        card.columnconfigure(0, weight=1)
        self._r += 1
        ctk.CTkLabel(card, text=title, font=theme.font(15, "bold"), text_color=theme.TEXT, anchor="w").grid(
            row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(16, 6))
        card._n = 1
        return card

    def _row(self, card, title: str, hint: str, widget) -> None:
        frame = ctk.CTkFrame(card, fg_color="transparent")
        frame.grid(row=card._n, column=0, columnspan=2, sticky="ew", padx=10, pady=5)
        frame.columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, font=theme.font(13, "medium"), text_color=theme.TEXT, anchor="w").grid(
            row=0, column=0, sticky="w", padx=10)
        ctk.CTkLabel(frame, text=hint, font=theme.font(11), text_color=theme.MUTED, anchor="w", justify="left",
                     wraplength=330).grid(row=1, column=0, sticky="w", padx=10)
        widget.grid(in_=frame, row=0, column=1, rowspan=2, padx=10)
        widget.tk.call("raise", str(widget))
        card._n += 1

    # ------------------------------------------------------------- actions
    def _pick_theme(self, value: str) -> None:
        for name, chip in self._chips:
            chip.set_selected(name == value)
        self._theme(value)

    def _theme(self, value: str) -> None:
        self.settings.set("theme", value)
        # Rebuild only after this chip's mouse callback has returned.
        self.app.request_theme_update(reopen_settings=True)

    def _pick_palette(self, value: str) -> None:
        for name, chip in self._palette_chips:
            chip.set_selected(name == value)
        self.settings.set("palette", value)
        from . import gfx  # the tinted artwork is cached per accent, so drop the stale copies
        gfx.reset_palette_cache()
        self.app.request_theme_update(reopen_settings=True)

    def _clip(self, value: str) -> None:
        self.settings.set("clipboard_clear_seconds", 0 if value == "Never" else int(value.split()[0]))

    def _new_recovery(self) -> None:
        if messagebox.askyesno("SecureVault", "Create a new recovery key?\nThe old recovery key will stop working."):
            RecoveryKeyDialog(self.winfo_toplevel(), self.db.rotate_recovery_key(), on_done=None)

    def _refresh_backup_info(self) -> None:
        backups = list_backups(self.app.backup_dir)
        last = fmt_ts(backups[0].stat().st_mtime) if backups else "never"
        self.backup_info.configure(text=f"{len(backups)} backup(s) stored · last backup: {last}")

    def _backup_now(self) -> None:
        try:
            make_backup(self.db, self.app.backup_dir, int(self.settings.get("backups_to_keep")))
        except OSError as exc:
            messagebox.showerror("SecureVault", f"Backup failed:\n{exc}")
            return
        self._refresh_backup_info()
        self.app.toast("Backup created")

    def _open_folder(self) -> None:
        self.app.backup_dir.mkdir(parents=True, exist_ok=True)
        open_path(self.app.backup_dir)

    def _restore(self) -> None:
        self.app.backup_dir.mkdir(parents=True, exist_ok=True)
        path = filedialog.askopenfilename(parent=self.winfo_toplevel(), title="Choose a backup to restore",
                                          initialdir=str(self.app.backup_dir), filetypes=[("Vault backup", "*.db")])
        if not path:
            return
        if not messagebox.askyesno(
                "SecureVault",
                "Replace your current vault with this backup?\n\nYour current vault is kept as a safety copy "
                "(vault.before-restore-….db). Everything changed after the backup was made will be missing.\n\n"
                "You will need the master password that was active when the backup was made."):
            return
        self.app.restore_backup(path)
