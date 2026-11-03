"""Welcome / create-vault screen: soft gradient backdrop, white card, animated hero panel."""
from __future__ import annotations

import threading
import time
import tkinter as tk

import customtkinter as ctk

from . import anim, gfx, theme
from .dialogs import RecoveryKeyDialog, RecoveryResetDialog, check_new_master
from .gfx import S
from .scene import Backdrop, HeroScene
from .theme import pick
from .widgets import GButton, SecretEntry, StrengthMeter

CARD_W = 440


class LoginFrame(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=theme.PAGE, corner_radius=0)
        self.app, self.db = app, app.db
        self.creating = not self.db.is_initialized()
        self.fails, self.locked_until, self._busy = 0, 0.0, False
        self._card_ph = None
        self.backdrop = Backdrop(self, on_resize=self._relayout)
        self.backdrop.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._card_item = self.backdrop.create_image(0, 0, anchor="nw")
        self.scene = HeroScene(
            self, bg="#D9DEFF",
            title="Your passwords,\nsafe & simple.",
            subtitle="Everything is encrypted with AES-256 and never leaves this computer.",
            animate=app.animations_enabled)
        self.content = tk.Frame(self, bg=pick(theme.CARD), bd=0, highlightthickness=0)
        self.content.columnconfigure(0, weight=1)
        self._build_create() if self.creating else self._build_unlock()
        self.after(150, self._focus)

    def _focus(self):
        try:
            self.pw.entry.focus_set()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- layout
    def _card_height(self) -> int:
        return 570 if self.creating else 480

    def _relayout(self, wp: int, hp: int) -> None:
        sc = gfx.scale()
        W, H = wp / sc, hp / sc
        margin = 44
        scene_w = min(W * 0.50, 640)
        scene_h = H - 2 * margin
        scene_x = W - margin - scene_w
        card_h = min(self._card_height(), H - 40)
        card_x = max(24, (scene_x - CARD_W) / 2 + 6)
        card_y = (H - card_h) / 2
        img = gfx.card_image(S(CARD_W), S(card_h), pick(theme.CARD), S(34), shadow=0.30)
        old = self._card_ph
        self._card_ph = gfx.photo(img)
        pad = S(gfx.SHADOW_PAD)
        self._card_base = (S(card_x) - pad, S(card_y) - pad)
        self.backdrop.coords(self._card_item, S(card_x) - pad, S(card_y) - pad)
        self.backdrop.itemconfigure(self._card_item, image=self._card_ph)
        if old is not None:
            gfx.release(old)
        inset = 26
        self._content_geo = dict(x=S(card_x + inset), y=S(card_y + inset), width=S(CARD_W - 2 * inset),
                                 height=S(card_h - 2 * inset))
        self.content.place(x=S(card_x + inset), y=S(card_y + inset), width=S(CARD_W - 2 * inset),
                           height=S(card_h - 2 * inset))
        self.scene.place(x=S(scene_x), y=S(margin), width=S(scene_w), height=S(scene_h))
        self.scene.configure(bg=self.backdrop.color_at(S(scene_x + scene_w / 2), S(margin / 2)))
        self.scene.bg_provider = self._scene_backdrop
        self.after(90, self.scene.force_layout)

    def shake_card(self) -> None:
        """Keep the card still; the inline error explains the failure."""
        return

    def _scene_backdrop(self, wp: int, hp: int):
        pil = self.backdrop._pil
        if pil is None:
            return None
        x, y = self.scene.winfo_x(), self.scene.winfo_y()
        return pil.crop((x, y, x + wp, y + hp))

    # ---------------------------------------------------------------- pieces
    def _header(self, title: str, subtitle: str) -> None:
        row = tk.Frame(self.content, bg=pick(theme.CARD))
        row.grid(row=0, column=0, sticky="w", pady=(2, 0))
        icon = tk.Label(row, bg=pick(theme.CARD), bd=0)
        self._logo = gfx.photo(gfx.sprite("app_icon", width=34))
        icon.configure(image=self._logo)
        icon.pack(side="left")
        tk.Label(row, text="SecureVault", bg=pick(theme.CARD), fg=pick(theme.TEXT), font=gfx.tkfont_for(15, "bold")).pack(
            side="left", padx=(10, 0))
        ctk.CTkLabel(self.content, text=title, font=theme.font(28, "bold"), text_color=theme.TEXT, anchor="w",
                     fg_color=theme.CARD).grid(row=1, column=0, sticky="ew", pady=(22, 0))
        ctk.CTkLabel(self.content, text=subtitle, font=theme.font(13), text_color=theme.MUTED, anchor="w",
                     justify="left", wraplength=CARD_W - 70, fg_color=theme.CARD).grid(
            row=2, column=0, sticky="ew", pady=(4, 14))

    def _footer(self, row: int) -> None:
        note = tk.Frame(self.content, bg=pick(theme.CARD))
        note.grid(row=row, column=0, sticky="s", pady=(8, 0))
        self.content.rowconfigure(row, weight=1)
        self._shield = gfx.photo(gfx.icon("shield_check", 16, pick(theme.MUTED)))
        tk.Label(note, image=self._shield, bg=pick(theme.CARD), bd=0).pack(side="left")
        tk.Label(note, text="AES-256 · scrypt · stays on this device", bg=pick(theme.CARD), fg=pick(theme.MUTED),
                 font=gfx.tkfont_for(11)).pack(side="left", padx=(6, 0))

    def _error_label(self, row: int):
        self.error = ctk.CTkLabel(self.content, text="", text_color=theme.DANGER, wraplength=CARD_W - 70,
                                  font=theme.font(12), anchor="w", justify="left", fg_color=theme.CARD)
        self.error.grid(row=row, column=0, sticky="ew", pady=(6, 0))

    def _say(self, text: str, error: bool = True) -> None:
        self.error.configure(text=text, text_color=theme.DANGER if error else theme.MUTED)

    # --------------------------------------------------------------- unlock
    def _build_unlock(self):
        self._header("Welcome back", "Unlock your encrypted vault with your master password.")
        self.pw = SecretEntry(self.content, copy=False, bg=theme.CARD, placeholder="Master password")
        self.pw.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.pw.entry.bind("<Return>", lambda _e: self._unlock())
        self._error_label(4)
        self.btn = GButton(self.content, "Unlock vault", self._unlock, width=CARD_W - 52, height=50, icon="unlock")
        self.btn.grid(row=5, column=0, pady=(10, 0))
        GButton(self.content, "Forgot password? Use recovery key", self._forgot, width=CARD_W - 52, height=38,
                style="ghost", size=12, weight="medium").grid(row=6, column=0, pady=(8, 0))
        self._footer(7)

    def _unlock(self):
        if self._busy:
            return
        password = self.pw.get()
        if not password:
            return
        wait = self.locked_until - time.time()
        if wait > 0:
            self._say(f"Too many attempts. Try again in {int(wait) + 1}s.")
            return
        self._busy = True
        self._say("Checking password…", error=False)
        self.btn.set_state("disabled")
        work = self.db.prepare_unlock(password)
        result: list = []
        threading.Thread(target=lambda: result.append(work()), daemon=True).start()
        self._poll(result)

    def _poll(self, result: list):
        if not self.winfo_exists():
            return
        if not result:
            self.after(25, lambda: self._poll(result))
            return
        dek = result[0]
        self._busy = False
        self.btn.set_state("normal")
        if dek is not None:
            self.fails = 0
            self.db.finish_unlock(dek)
            self._say("")
            self.scene.play_unlock(self.app.on_unlocked)
            return
        self.fails += 1
        self.pw.set("")
        self.scene.shake()
        self.shake_card()
        if self.fails >= 5:
            delay = min(60, 2 ** (self.fails - 4))
            self.locked_until = time.time() + delay
            self._say(f"Incorrect password. Please wait {delay}s before trying again.")
        else:
            self._say("Incorrect password. Try again.")

    def _forgot(self):
        RecoveryResetDialog(self.app, self.db, on_success=self.app.on_unlocked)

    # --------------------------------------------------------------- create
    def _build_create(self):
        self._header("Create your vault", "One master password protects everything. You will get a recovery key next.")
        self.pw = SecretEntry(self.content, copy=False, bg=theme.CARD, placeholder="Create master password",
                              on_change=lambda: self.meter.update_for(self.pw.get()))
        self.pw.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        self.meter = StrengthMeter(self.content, bg=theme.CARD, width=CARD_W - 60)
        self.meter.grid(row=4, column=0, sticky="w", pady=(8, 4))
        self.confirm = SecretEntry(self.content, copy=False, bg=theme.CARD, placeholder="Confirm master password")
        self.confirm.grid(row=5, column=0, sticky="ew", pady=(4, 0))
        self.confirm.entry.bind("<Return>", lambda _e: self._create())
        self._error_label(6)
        self.btn = GButton(self.content, "Create secure vault", self._create, width=CARD_W - 52, height=50, icon="lock")
        self.btn.grid(row=7, column=0, pady=(10, 0))
        self._footer(8)

    def _create(self):
        problem = check_new_master(self.pw.get(), self.confirm.get())
        if problem:
            self._say(problem)
            return
        self._say("Creating encrypted vault…", error=False)
        self.btn.set_state("disabled")
        self.update_idletasks()
        try:
            recovery = self.db.create(self.pw.get())
        finally:
            self.btn.set_state("normal")
        RecoveryKeyDialog(self.app, recovery, on_done=lambda: self.scene.play_unlock(self.app.on_unlocked))
