"""Application window: screen switching, auto-lock, clipboard hygiene, tray, theme."""
from __future__ import annotations

import queue
import sys
import time
import tkinter as tk
import traceback
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

from .. import APP_NAME
from ..backup import auto_backup_if_needed
from ..database import VaultDB
from ..settings import Settings, data_dir
from ..tray import Tray
from . import anim, gfx, theme
from .gfx import S
from .login import LoginFrame
from .main_view import MainView

TOAST_KEY = "#010203"          # colour key for the rounded toast on Windows


class VaultApp(ctk.CTk):
    def __init__(self, instance=None, start_hidden: bool = False):
        self.data_dir = data_dir()
        self.settings = Settings(self.data_dir / "settings.json")
        self.backup_dir = self.data_dir / "backups"
        ctk.set_appearance_mode(self.settings.get("theme"))
        theme.apply_palette(self.settings.get("palette"))
        ctk.set_default_color_theme("blue")
        super().__init__(fg_color=theme.PAGE)
        gfx.init(self)
        anim.init(self, lambda: self.settings.get("animations"))
        anim.init_icons(lambda: self.settings.get("icon_motion"))
        self.instance = instance
        self.db = VaultDB(self.data_dir / "vault.db")
        self.events: queue.Queue = queue.Queue()
        self.main: MainView | None = None
        self.login: LoginFrame | None = None
        self.last_activity = time.time()
        self._clip_job, self._clip_value = None, None
        self._toast = None
        self._toast_job = None
        self._theme_job = None

        self.title(APP_NAME)
        w, h = 1240, 780
        sc = gfx.scale()
        x = max(0, (self.winfo_screenwidth() - int(w * sc)) // 2)
        y = max(0, (self.winfo_screenheight() - int(h * sc)) // 3)
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(1140, 680)
        self.ico_path = self.data_dir / "securevault.ico"
        if not self.ico_path.exists():
            gfx.make_ico(self.ico_path)
        if sys.platform.startswith("win") and self.ico_path.exists():
            self.after(300, self._set_icon)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        for seq in ("<Key>", "<Button>", "<Motion>", "<MouseWheel>"):
            self.bind_all(seq, self._touch, add="+")
        self.bind_all("<Control-l>", lambda _e: self.lock(), add="+")
        self.bind_all("<Control-n>", lambda _e: self.main and self.main.open_new(), add="+")
        self.bind_all("<Control-f>", lambda _e: self.main and self.main.search.focus_set(), add="+")

        self.tray = Tray(self.events)
        self.tray.start()
        if instance is not None:
            instance.serve(self.events.put)
        self.show_login()
        self._fade_in_window()
        self.after(1000, self._tick)
        self.after(250, self._poll_events)
        if start_hidden and self.tray.available:
            self.after(50, self.withdraw)

    # ----------------------------------------------------------- utilities
    def _fade_in_window(self) -> None:
        """Fade the whole window in on start-up (needs compositing; silently skipped elsewhere)."""
        if not self.animations_enabled():
            return
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            return

        def step(t: float) -> None:
            self.attributes("-alpha", min(1.0, t))
        anim.start("window-fade", 320, step, ease=anim.ease_out, delay_ms=40,
                   done=lambda: self.attributes("-alpha", 1.0))

    def _set_icon(self) -> None:
        try:
            self.iconbitmap(str(self.ico_path))
        except Exception:  # noqa: BLE001
            pass

    def animations_enabled(self) -> bool:
        return bool(self.settings.get("animations"))

    def _touch(self, _event=None) -> None:
        self.last_activity = time.time()

    def report_callback_exception(self, exc, val, tb) -> None:
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            with open(self.data_dir / "error.log", "a", encoding="utf-8") as fh:
                fh.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n{text}\n")
        except OSError:
            pass
        print(text, file=sys.stderr)
        try:
            self.toast("Something went wrong (details saved to error.log)", error=True)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------- screens
    def _clear_screens(self) -> None:
        for frame in (self.main, self.login):
            if frame is not None:
                frame.destroy()
        self.main = self.login = None

    def show_login(self) -> None:
        def swap():
            self._clear_screens()
            self.login = LoginFrame(self, self)
            self.login.pack(fill="both", expand=True)
        if self.main is not None or self.login is not None:
            anim.crossfade(self, swap, ms=300)
        else:
            swap()

    def on_unlocked(self) -> None:
        try:
            self.db.purge_old_trash()
            if self.settings.get("auto_backup"):
                auto_backup_if_needed(self.db, self.backup_dir, int(self.settings.get("backups_to_keep")))
        except OSError:
            pass

        def swap():
            self._clear_screens()
            self.main = MainView(self, self)
            self.main.pack(fill="both", expand=True)
        anim.crossfade(self, swap, ms=420)
        self.last_activity = time.time()
        if self.db.unreadable:
            messagebox.showwarning(
                APP_NAME, f"{self.db.unreadable} entr{'y' if self.db.unreadable == 1 else 'ies'} could not be read "
                          "and were skipped. Restoring a backup may bring them back.")

    def request_theme_update(self, reopen_settings: bool = False) -> None:
        """Coalesce rapid choices and avoid destroying widgets inside their click handler."""
        if self._theme_job is not None:
            self.after_cancel(self._theme_job)
        self._theme_job = self.after_idle(lambda: self._apply_pending_theme(reopen_settings))

    def _apply_pending_theme(self, reopen_settings: bool) -> None:
        self._theme_job = None
        self.apply_theme(reopen_settings)

    def apply_theme(self, reopen_settings: bool = False) -> None:
        # Save state and dispose the old UI before CustomTkinter broadcasts a mode
        # change. Avoid screenshot overlays and nested update() during the rebuild.
        state = self.main.get_state() if self.main is not None else None
        if self.main is not None:
            old_main, self.main = self.main, None
            old_main.destroy()
        ctk.set_appearance_mode(self.settings.get("theme"))
        theme.apply_palette(self.settings.get("palette"))
        self.configure(fg_color=theme.PAGE)
        if state is not None:
            self.main = MainView(self, self)
            self.main.pack(fill="both", expand=True)
            self.main.set_state(state)
            if reopen_settings:
                self.main.open_settings(fade=False)

    # ---------------------------------------------------------------- lock
    def lock(self) -> None:
        if not self.db.unlocked and self.main is None:
            return
        self._wipe_clipboard(force=False)
        self.db.lock()
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        self.show_login()

    def _tick(self) -> None:
        self.after(1000, self._tick)
        if self.main is None:
            return
        minutes = int(self.settings.get("autolock_minutes"))
        remaining = minutes * 60 - (time.time() - self.last_activity)
        if remaining <= 0:
            self.lock()
            return
        if self.settings.get("lock_on_minimize") and self.state() == "iconic":
            self.lock()
            return
        m, s = divmod(int(remaining), 60)
        try:
            self.main.sidebar.set_lock_text(f"Auto-lock in {m}:{s:02d}")
        except tk.TclError:
            pass

    # ------------------------------------------------------- tray / closing
    def _poll_events(self) -> None:
        self.after(250, self._poll_events)
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            if event == "open":
                self.deiconify()
                self.lift()
                self.focus_force()
            elif event == "lock":
                self.lock()
            elif event == "quit":
                self.quit_app()

    def on_close(self) -> None:
        if self.tray.available:
            if self.settings.get("lock_on_close"):
                self.lock()
            self.withdraw()
        else:
            self.quit_app()

    def quit_app(self) -> None:
        self._wipe_clipboard(force=False)
        self.tray.stop()
        try:
            self.db.close()
        finally:
            if self.instance is not None:
                self.instance.close()
            self.destroy()

    # ------------------------------------------------------------ clipboard
    def copy_to_clipboard(self, text: str, secret: bool = False) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()
        if self._clip_job:
            self.after_cancel(self._clip_job)
            self._clip_job = None
        seconds = int(self.settings.get("clipboard_clear_seconds"))
        if secret and seconds > 0 and text:
            self._clip_value = text
            self._clip_job = self.after(seconds * 1000, lambda: self._wipe_clipboard(force=True))
            self.toast(f"Copied · clears in {seconds}s")
        else:
            self.toast("Copied")

    def _wipe_clipboard(self, force: bool) -> None:
        if self._clip_job:
            try:
                self.after_cancel(self._clip_job)
            except tk.TclError:
                pass
            self._clip_job = None
        value, self._clip_value = self._clip_value, None
        if not value:
            return
        try:
            if self.clipboard_get() == value:
                self.clipboard_clear()
                self.clipboard_append("")
                self.update()
        except tk.TclError:
            pass

    # --------------------------------------------------------------- backups
    def restore_backup(self, path) -> None:
        try:
            safety = self.db.replace_with(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, f"Restore failed:\n{exc}")
            return
        self.show_login()
        messagebox.showinfo(APP_NAME, f"Backup restored.\nYour previous vault was saved as:\n{safety.name}\n\n"
                                      "Unlock with the master password that belonged to that backup.")

    # ----------------------------------------------------------------- toast
    def toast(self, text: str, error: bool = False) -> None:
        if self._toast is not None:
            try:
                self._toast.destroy()
            except tk.TclError:
                pass
        if self._toast_job:
            self.after_cancel(self._toast_job)
        anim.cancel("toast")
        label = gfx.text_image(text, 13, "#FFFFFF", "medium")
        icon = gfx.icon("x" if error else "check", 16, "#FFFFFF")
        pad = S(18)
        w = pad * 2 + icon.width + S(10) + label.width
        h = S(46)
        fill = "#D9363E" if error else "#1C1647"
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        img.alpha_composite(gfx.card_image(w, h, fill, h // 2, None))
        img.alpha_composite(icon, (pad, (h - icon.height) // 2))
        img.alpha_composite(label, (pad + icon.width + S(10), (h - label.height) // 2 - S(1)))
        top = tk.Toplevel(self)
        top.overrideredirect(True)
        top.attributes("-topmost", True)
        canvas = tk.Canvas(top, width=w, height=h, highlightthickness=0, bd=0,
                           bg=TOAST_KEY if sys.platform.startswith("win") else fill)
        canvas.pack()
        ph = gfx.photo(img)
        canvas.create_image(0, 0, anchor="nw", image=ph)
        canvas.image = ph
        if sys.platform.startswith("win"):
            top.attributes("-transparentcolor", TOAST_KEY)
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + self.winfo_height() - h - S(36)
        self._toast = top
        rise = S(16)

        def place(offset: int, alpha: float) -> None:
            try:
                top.geometry(f"{w}x{h}+{x}+{y + offset}")
                top.attributes("-alpha", alpha)
            except tk.TclError:
                pass
        place(rise, 0.0)
        anim.start("toast", 260, lambda t: place(int(rise * (1 - t)), t), ease=anim.ease_out)
        self._toast_job = self.after(2300, self._hide_toast)

    def _hide_toast(self) -> None:
        top = self._toast
        if top is None:
            return
        try:
            x, y = top.winfo_x(), top.winfo_y()
        except tk.TclError:
            self._toast = None
            return
        drop = S(10)

        def step(t: float) -> None:
            try:
                top.geometry(f"+{x}+{y + int(drop * t)}")
                top.attributes("-alpha", 1.0 - t)
            except tk.TclError:
                pass

        def done() -> None:
            try:
                top.destroy()
            except tk.TclError:
                pass
            if self._toast is top:
                self._toast = None
        anim.start("toast", 220, step, done=done, ease=anim.ease_in_out)
