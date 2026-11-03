"""Modal dialogs in the lavender style."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ..passwords import generate_password, strength
from . import anim, gfx, theme
from .capslock import attach_caps_hint
from .widgets import GButton, SecretEntry, StrengthMeter, copy_text, entry

MIN_MASTER_LEN = 10


def check_new_master(password: str, confirm: str) -> str | None:
    """Return an error message, or None if the new master password is acceptable."""
    if len(password) < MIN_MASTER_LEN:
        return f"Use at least {MIN_MASTER_LEN} characters."
    if password != confirm:
        return "The two passwords do not match."
    if strength(password)[0] == 0:
        return "That password is too weak. Try a longer passphrase."
    return None


class ModalDialog(ctk.CTkToplevel):
    def __init__(self, master, title: str, width: int = 460, height: int = 360, heading: str | None = None,
                 subtitle: str | None = None):
        super().__init__(master, fg_color=theme.CARD)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        master.update_idletasks()
        sc = gfx.scale()
        x = master.winfo_rootx() + (master.winfo_width() - int(width * sc)) // 2
        y = master.winfo_rooty() + (master.winfo_height() - int(height * sc)) // 3
        self.geometry(f"{width}x{height}+{max(x, 0)}+{max(y, 0)}")
        self.columnconfigure(0, weight=1)
        self._row = 0
        self.after(120, self._grab)
        self.after(260, self._set_icon)
        self._fade_in(x, y)
        if heading:
            self.heading(heading, subtitle)

    def _fade_in(self, x: int, y: int) -> None:
        """Soft entrance: the dialog fades in while rising a few pixels (needs window compositing)."""
        if not anim.enabled():
            return
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            return
        rise = gfx.S(14)

        def step(t: float) -> None:
            try:
                self.geometry(f"+{max(x, 0)}+{max(y, 0) + int(rise * (1 - t))}")
                self.attributes("-alpha", t)
            except tk.TclError:
                pass
        anim.start(("dialog", id(self)), 240, step, ease=anim.ease_out, delay_ms=30,
                   done=lambda: self._finish_fade())

    def _finish_fade(self) -> None:
        try:
            self.attributes("-alpha", 1.0)
        except tk.TclError:
            pass

    def _set_icon(self) -> None:
        icon = getattr(self.master, "ico_path", None) or getattr(self.winfo_toplevel(), "ico_path", None)
        try:
            if icon:
                self.iconbitmap(str(icon))
        except Exception:  # noqa: BLE001
            pass

    def _grab(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def heading(self, text: str, subtitle: str | None = None) -> None:
        ctk.CTkLabel(self, text=text, font=theme.font(20, "bold"), text_color=theme.TEXT, anchor="w").grid(
            row=self._row, column=0, sticky="ew", padx=28, pady=(26, 0))
        self._row += 1
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=theme.font(12), text_color=theme.MUTED, anchor="w",
                         justify="left", wraplength=400).grid(row=self._row, column=0, sticky="ew", padx=28, pady=(4, 6))
            self._row += 1

    def place_row(self, widget, pady=(10, 0), padx=28, sticky="ew") -> None:
        widget.grid(row=self._row, column=0, sticky=sticky, padx=padx, pady=pady)
        self._row += 1
        if isinstance(widget, ctk.CTkEntry):
            attach_caps_hint(widget, self, self._row, padx=padx, pady=(2, 0))
            self._row += 1

    def label(self, text: str) -> None:
        ctk.CTkLabel(self, text=text, font=theme.font(12, "medium"), text_color=theme.MUTED, anchor="w").grid(
            row=self._row, column=0, sticky="ew", padx=30, pady=(12, 0))
        self._row += 1


class PasswordGeneratorDialog(ModalDialog):
    def __init__(self, master, on_use):
        super().__init__(master, "Password generator", 480, 500, "Password generator",
                         "Create a strong random password.")
        self.on_use = on_use
        self.entry = entry(self, height=46, font=ctk.CTkFont(family="Consolas", size=15))
        self.place_row(self.entry, pady=(12, 0))
        self.meter = StrengthMeter(self, width=400)
        self.place_row(self.meter, pady=(8, 0))
        self.length_label = ctk.CTkLabel(self, text="Length: 20", font=theme.font(12, "medium"), text_color=theme.TEXT,
                                         anchor="w")
        self.place_row(self.length_label, pady=(10, 0))
        self.length = ctk.CTkSlider(self, from_=8, to=64, number_of_steps=56, command=self._regen,
                                    progress_color=theme.PRIMARY, button_color=theme.PRIMARY,
                                    button_hover_color=theme.PRIMARY_HOVER, fg_color=theme.BORDER)
        self.length.set(20)
        self.place_row(self.length, pady=(2, 0))
        self.vars = {}
        opts = ctk.CTkFrame(self, fg_color="transparent")
        self.place_row(opts, pady=(10, 0))
        for i, (key, label, default) in enumerate((("upper", "A-Z", True), ("lower", "a-z", True),
                                                  ("digits", "0-9", True), ("symbols", "!@#$", True),
                                                  ("ambiguous", "Avoid look-alikes", False))):
            var = tk.BooleanVar(value=default)
            self.vars[key] = var
            ctk.CTkCheckBox(opts, text=label, variable=var, command=self._regen, font=theme.font(12),
                            text_color=theme.TEXT, fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER,
                            border_color=theme.BORDER, corner_radius=8, checkbox_width=22, checkbox_height=22).grid(
                row=i // 2, column=i % 2, sticky="w", padx=(0, 22), pady=5)
        self.error = ctk.CTkLabel(self, text="", text_color=theme.DANGER, font=theme.font(12))
        self.place_row(self.error, pady=(4, 0))
        btns = ctk.CTkFrame(self, fg_color="transparent")
        self.place_row(btns, pady=(6, 18))
        GButton(btns, "Regenerate", self._regen, width=120, height=42, style="soft", icon="refresh", size=12).pack(
            side="left", padx=(0, 8))
        GButton(btns, "Copy", lambda: copy_text(self, self.entry.get(), True), width=90, height=42, style="soft",
                size=12).pack(side="left", padx=(0, 8))
        GButton(btns, "Use password", self._use, width=150, height=42, style="primary", icon="check", size=12).pack(
            side="left")
        self._regen()

    def _regen(self, *_args) -> None:
        length = int(self.length.get())
        self.length_label.configure(text=f"Length: {length}")
        try:
            pw = generate_password(length, upper=self.vars["upper"].get(), lower=self.vars["lower"].get(),
                                   digits=self.vars["digits"].get(), symbols=self.vars["symbols"].get(),
                                   avoid_ambiguous=self.vars["ambiguous"].get())
        except ValueError as exc:
            self.error.configure(text=str(exc))
            return
        self.error.configure(text="")
        self.entry.delete(0, "end")
        self.entry.insert(0, pw)
        self.meter.update_for(pw)

    def _use(self) -> None:
        self.on_use(self.entry.get())
        self.destroy()


class RecoveryKeyDialog(ModalDialog):
    """Shows the recovery key once; cannot be dismissed until the user confirms."""

    def __init__(self, master, key_text: str, on_done):
        super().__init__(master, "Your recovery key", 540, 430, "Save your recovery key",
                         "It is the ONLY way to open your vault if you forget the master password. "
                         "Print it or keep it somewhere safe. Anyone who has it can open your vault.")
        self.on_done, self.key_text = on_done, key_text
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        field = entry(self, height=52, font=ctk.CTkFont(family="Consolas", size=15), justify="center")
        field.insert(0, key_text)
        field.configure(state="readonly")
        self.place_row(field, pady=(12, 0))
        row = ctk.CTkFrame(self, fg_color="transparent")
        self.place_row(row, pady=(12, 0))
        GButton(row, "Copy", lambda: copy_text(self, key_text), width=100, height=40, style="soft", icon="copy",
                size=12).pack(side="left", padx=(0, 8))
        GButton(row, "Save to file…", self._save, width=140, height=40, style="soft", icon="download", size=12).pack(
            side="left")
        self.confirm = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(self, text="I have stored my recovery key safely", variable=self.confirm, command=self._toggle,
                        font=theme.font(12), text_color=theme.TEXT, fg_color=theme.PRIMARY,
                        hover_color=theme.PRIMARY_HOVER, border_color=theme.BORDER, corner_radius=8).grid(
            row=self._row, column=0, pady=(20, 6), padx=28, sticky="w")
        self._row += 1
        self.btn = GButton(self, "Continue", self._finish, width=200, height=46, style="primary")
        self.btn.set_state("disabled")
        self.place_row(self.btn, pady=(8, 20), sticky="")

    def _toggle(self) -> None:
        self.btn.set_state("normal" if self.confirm.get() else "disabled")

    def _save(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".txt",
                                            initialfile="SecureVault-recovery-key.txt", filetypes=[("Text", "*.txt")])
        if path:
            try:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(f"SecureVault recovery key:\n{self.key_text}\n")
            except OSError as exc:
                messagebox.showerror("SecureVault", f"Could not save the file:\n{exc}", parent=self)

    def _finish(self) -> None:
        if not self.confirm.get():
            return
        self.destroy()
        if self.on_done:
            self.on_done()


class ChangePasswordDialog(ModalDialog):
    def __init__(self, master, db):
        super().__init__(master, "Change master password", 460, 520, "Change master password",
                         "Choose a long passphrase you can remember.")
        self.db = db
        self.label("Current master password")
        self.current = SecretEntry(self, copy=False)
        self.place_row(self.current, pady=(4, 0))
        self.label("New master password")
        self.new = SecretEntry(self, copy=False, on_change=lambda: self.meter.update_for(self.new.get()))
        self.place_row(self.new, pady=(4, 0))
        self.meter = StrengthMeter(self, width=400)
        self.place_row(self.meter, pady=(8, 0))
        self.label("Confirm new password")
        self.confirm = SecretEntry(self, copy=False)
        self.place_row(self.confirm, pady=(4, 0))
        self.error = ctk.CTkLabel(self, text="", text_color=theme.DANGER, wraplength=390, font=theme.font(12))
        self.place_row(self.error, pady=(8, 0))
        self.btn = GButton(self, "Change password", self._apply, width=220, height=46, style="primary")
        self.place_row(self.btn, pady=(6, 20), sticky="")

    def _apply(self) -> None:
        problem = check_new_master(self.new.get(), self.confirm.get())
        if problem:
            self.error.configure(text=problem)
            return
        self.error.configure(text="Working…", text_color=theme.MUTED)
        self.update_idletasks()
        if not self.db.change_master_password(self.current.get(), self.new.get()):
            self.error.configure(text="The current master password is wrong.", text_color=theme.DANGER)
            return
        self.destroy()
        messagebox.showinfo("SecureVault", "Master password changed.\n\nNote: older backups still open with the "
                                           "password that was active when they were made.")


class RecoveryResetDialog(ModalDialog):
    """Forgot master password: use the recovery key and choose a new password."""

    def __init__(self, master, db, on_success):
        super().__init__(master, "Reset with recovery key", 480, 560, "Reset with recovery key",
                         "Enter the recovery key you saved when you created the vault.")
        self.db, self.on_success = db, on_success
        self.label("Recovery key")
        self.key = entry(self, "XXXXX-XXXXX-XXXXX-…", height=44)
        self.place_row(self.key, pady=(4, 0))
        self.label("New master password")
        self.new = SecretEntry(self, copy=False, on_change=lambda: self.meter.update_for(self.new.get()))
        self.place_row(self.new, pady=(4, 0))
        self.meter = StrengthMeter(self, width=420)
        self.place_row(self.meter, pady=(8, 0))
        self.label("Confirm new password")
        self.confirm = SecretEntry(self, copy=False)
        self.place_row(self.confirm, pady=(4, 0))
        self.error = ctk.CTkLabel(self, text="", text_color=theme.DANGER, wraplength=410, font=theme.font(12))
        self.place_row(self.error, pady=(8, 0))
        self.btn = GButton(self, "Reset and unlock", self._apply, width=220, height=46, style="primary")
        self.place_row(self.btn, pady=(6, 20), sticky="")

    def _apply(self) -> None:
        problem = check_new_master(self.new.get(), self.confirm.get())
        if problem:
            self.error.configure(text=problem)
            return
        self.error.configure(text="Working…", text_color=theme.MUTED)
        self.update_idletasks()
        if not self.db.unlock_with_recovery(self.key.get(), self.new.get()):
            self.error.configure(text="That recovery key is not correct.", text_color=theme.DANGER)
            return
        self.destroy()
        self.on_success()
