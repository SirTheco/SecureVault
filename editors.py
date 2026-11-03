"""Main screen: sidebar + account list + detail panel."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from ..database import Item
from ..passwords import strength
from . import anim, gfx, theme
from .capslock import attach_caps_hint
from .editors import EDITORS
from .gfx import S
from .rows import AccountRow
from .scene import HeroScene
from .settings_panel import SettingsPanel
from .sidebar import Sidebar
from .theme import pick
from .widgets import Chip, GButton, IconButton, copy_text

MAX_ROWS = 300
OLD_DAYS = 365
VIEW_TITLES = {"all": "All items", "favorites": "Favorites", "attention": "Security check"}
CHIP_GRADS = (theme.TEAL_GRAD, theme.PINK_GRAD, theme.ORANGE_GRAD, theme.BLUE_GRAD, theme.PRIMARY_GRAD)


def search_text(item: Item) -> str:
    """Searchable text of an item (secret values such as passwords are excluded)."""
    d = item.data
    parts = [d.get("title", ""), " ".join(d.get("tags", [])), d.get("username", ""), d.get("url", ""), d.get("notes", "")]
    for f in d.get("fields", []):
        parts.append(f.get("label", ""))
        if not f.get("secret"):
            parts.append(f.get("value", ""))
    return "\n".join(parts).lower()


def subtitle(item: Item) -> str:
    d = item.data
    return (d.get("username") or d.get("url") or "")[:80]


def find_issues(items: list[Item]) -> dict[int, list[str]]:
    """Per-item security flags: weak, reused, old."""
    seen: dict[str, int] = {}
    for it in items:
        pw = it.data.get("password") or ""
        if pw:
            seen[pw] = seen.get(pw, 0) + 1
    issues: dict[int, list[str]] = {}
    now = time.time()
    for it in items:
        flags = []
        pw = it.data.get("password") or ""
        if pw and strength(pw)[0] <= 1:
            flags.append("weak")
        if pw and seen.get(pw, 0) > 1:
            flags.append("reused")
        if pw and now - it.updated_at > OLD_DAYS * 86400:
            flags.append("old")
        if flags:
            issues[it.id] = flags
    return issues


class MainView(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=theme.PAGE, corner_radius=0)
        self.app, self.db = app, app.db
        self.items: list[Item] = []
        self.issues: dict[int, list[str]] = {}
        self.view = "all"
        self.tag_filter: str | None = None
        self.selected_id: int | None = None
        self.in_settings = False
        self._animate_rows = True
        self.row_widgets: dict = {}
        self.current_editor = None
        self._hero_scene = None
        self._search_job = None
        self.columnconfigure(2, weight=1)
        self.rowconfigure(0, weight=1)
        self.sidebar = Sidebar(self, self.set_view, self.open_settings, self.app.lock)
        self.sidebar.grid(row=0, column=0, sticky="ns", padx=(14, 0), pady=14)
        self._build_list()
        self.detail = ctk.CTkFrame(self, fg_color=theme.CARD, corner_radius=30, bg_color=theme.PAGE)
        self.detail.grid(row=0, column=2, sticky="nsew", padx=(0, 14), pady=14)
        self.detail.rowconfigure(0, weight=1)
        self.detail.columnconfigure(0, weight=1)
        self.reload()
        self.show_empty(fade=False)

    # --------------------------------------------------------------- build
    def _build_list(self) -> None:
        col = ctk.CTkFrame(self, width=372, fg_color=theme.CARD, corner_radius=30, bg_color=theme.PAGE)
        col.grid(row=0, column=1, sticky="ns", padx=14, pady=14)
        col.grid_propagate(False)
        col.rowconfigure(4, weight=1)
        col.columnconfigure(0, weight=1)
        head = ctk.CTkFrame(col, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 0))
        head.columnconfigure(0, weight=1)
        self.title_label = ctk.CTkLabel(head, text="Your Vault", font=theme.font(24, "bold"), text_color=theme.TEXT, anchor="w")
        self.title_label.grid(row=0, column=0, sticky="w")
        self.count_label = ctk.CTkLabel(head, text="", font=theme.font(12), text_color=theme.MUTED, anchor="w")
        self.count_label.grid(row=1, column=0, sticky="w")
        self.sort_btn = IconButton(head, "clock", self._toggle_sort, size=40, icon_size=20, bg=theme.CARD,
                                   tooltip="Sort")
        self.sort_btn.grid(row=0, column=1, rowspan=2)
        # search pill
        pill = ctk.CTkFrame(col, fg_color=theme.INPUT, corner_radius=22, height=46, bg_color=theme.CARD)
        pill.grid(row=1, column=0, sticky="ew", padx=22, pady=(16, 0))
        pill.columnconfigure(1, weight=1)
        self._search_icon = gfx.photo(gfx.icon("search", 18, pick(theme.MUTED)))
        tk.Label(pill, image=self._search_icon, bg=pick(theme.INPUT), bd=0).grid(row=0, column=0, padx=(14, 4), pady=10)
        self.search = ctk.CTkEntry(pill, placeholder_text="Search accounts…", fg_color=theme.INPUT, border_width=0,
                                   height=40, corner_radius=18, text_color=theme.TEXT,
                                   placeholder_text_color=theme.MUTED, font=theme.font(13))
        self.search.grid(row=0, column=1, sticky="ew", padx=(0, 20))
        self.search.bind("<KeyRelease>", self._on_search)
        attach_caps_hint(self.search, pill, row=1, column=1, pady=(2, 0))
        self.chip_row = ctk.CTkFrame(col, fg_color="transparent")
        self.chip_row.grid(row=2, column=0, sticky="ew", padx=22, pady=(12, 0))
        self.list_title = ctk.CTkLabel(col, text="", font=theme.font(12, "medium"), text_color=theme.MUTED, anchor="w")
        self.list_title.grid(row=3, column=0, sticky="ew", padx=24, pady=(10, 2))
        self.list_frame = anim.SmoothScrollFrame(col, fg_color=theme.CARD, scrollbar_button_color=theme.BORDER,
                                                 scrollbar_button_hover_color=theme.PRIMARY, corner_radius=0)
        self.list_frame.grid(row=4, column=0, sticky="nsew", padx=(14, 8))
        self.list_frame.columnconfigure(0, weight=1)
        GButton(col, "Add new account", lambda: self.open_new("account"), width=328, height=52, icon="plus").grid(
            row=5, column=0, pady=(10, 20))

    # ---------------------------------------------------------------- data
    def reload(self) -> None:
        self.items = self.db.get_items(kind="account")
        self.issues = find_issues(self.items)
        self._refresh_all()

    def find(self, item_id: int) -> Item | None:
        return next((i for i in self.items if i.id == item_id), None)

    def visible_items(self) -> list[Item]:
        query = self.search.get().strip().lower()
        pool = self.items
        if query:
            pool = [i for i in pool if query in search_text(i)]
        elif self.view == "favorites":
            pool = [i for i in pool if i.data.get("favorite")]
        elif self.view == "attention":
            pool = [i for i in pool if i.id in self.issues]
        if self.tag_filter:
            pool = [i for i in pool if self.tag_filter in i.data.get("tags", [])]
        if self.app.settings.get("sort") == "name":
            pool = sorted(pool, key=lambda i: i.title.lower())
        return pool

    def _tag_counts(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for it in self.items:
            for tag in it.data.get("tags", []):
                counts[tag] = counts.get(tag, 0) + 1
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))

    # ----------------------------------------------------------- rendering
    def _refresh_all(self) -> None:
        self._refresh_sidebar()
        self._refresh_chips()
        self._refresh_list()

    def _refresh_sidebar(self) -> None:
        favs = sum(1 for i in self.items if i.data.get("favorite"))
        self.sidebar.set_counts({"all": len(self.items), "favorites": favs, "attention": len(self.issues)})
        self.sidebar.set_active("settings" if self.in_settings else self.view)

    def _refresh_chips(self) -> None:
        specs = [("All", "view", "all"), ("Favorites", "view", "favorites")]
        specs += [(tag[:14], "tag", tag) for tag, _n in self._tag_counts()[:2]]
        sig = tuple(specs)

        def is_selected(kind: str, key: str) -> bool:
            if kind == "view":
                return self.tag_filter is None and self.view == key
            return self.tag_filter == key
        if getattr(self, "_chip_sig", None) == sig:        # same chips: just fade the selection
            for chip, (_l, kind, key) in zip(self._chips, specs):
                chip.set_selected(is_selected(kind, key))
            return
        self._chip_sig = sig
        for w in self.chip_row.winfo_children():
            w.destroy()
        self._chips = []
        for i, (label, kind, key) in enumerate(specs):
            cmd = (lambda v=key: self._chip_view(v)) if kind == "view" else (lambda t=key: self._chip_tag(t))
            chip = Chip(self.chip_row, label, cmd, selected=is_selected(kind, key), grad=CHIP_GRADS[i % len(CHIP_GRADS)],
                        bg=theme.CARD)
            chip.pack(side="left", padx=(0, 6))
            self._chips.append(chip)

    def _chip_view(self, view: str) -> None:
        self.tag_filter = None
        self.set_view(view)

    def _chip_tag(self, tag: str) -> None:
        self.tag_filter = None if self.tag_filter == tag else tag
        self.view = "all"
        self._refresh_all()

    def _refresh_list(self) -> None:
        for w in self.list_frame.winfo_children():
            w.destroy()
        items = self.visible_items()
        query = self.search.get().strip()
        base = VIEW_TITLES.get(self.view, "All items")
        label = f"Search results · {len(items)}" if query else f"{base} · {len(items)}"
        if self.tag_filter and not query:
            label = f"#{self.tag_filter} · {len(items)}"
        self.list_title.configure(text=label)
        self.count_label.configure(text=f"{len(self.items)} account{'s' if len(self.items) != 1 else ''} protected")
        self.sort_btn.set_icon("clock" if self.app.settings.get("sort") == "recent" else "file")
        if not items:
            if query:
                msg = "No matches."
            elif self.view == "attention":
                msg = "Everything looks healthy.\nNo weak or reused passwords."
            elif self.view == "favorites":
                msg = "No favorites yet.\nTap the star on an account."
            else:
                msg = "Nothing here yet.\nUse “Add new account”."
            ctk.CTkLabel(self.list_frame, text=msg, font=theme.font(13), text_color=theme.MUTED, justify="center").pack(pady=50)
        animate = self._animate_rows
        self._animate_rows = False
        self.row_widgets = {}
        for i, item in enumerate(items[:MAX_ROWS]):
            row = AccountRow(self.list_frame, item, subtitle(item), item.id == self.selected_id, self.issues.get(item.id, []),
                             self.open_item, self.toggle_favorite, self._copy_password,
                             reveal_delay=(40 + i * 38) if (animate and i < 9) else None)
            row.pack(fill="x", pady=4, padx=(0, 4))
            self.row_widgets[item.id] = row
        if len(items) > MAX_ROWS:
            ctk.CTkLabel(self.list_frame, text=f"Showing first {MAX_ROWS} of {len(items)}. Refine your search.",
                         font=theme.font(12), text_color=theme.MUTED).pack(pady=8)

    def _on_search(self, *_args) -> None:
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(160, self._refresh_list)

    def _toggle_sort(self) -> None:
        self.app.settings.set("sort", "name" if self.app.settings.get("sort") == "recent" else "recent")
        self._refresh_list()
        self.toast("Sorted by name" if self.app.settings.get("sort") == "name" else "Sorted by recent")

    # ---------------------------------------------------------- navigation
    def confirm_discard(self) -> bool:
        ed = self.current_editor
        if ed is not None and ed.is_dirty():
            return messagebox.askyesno("SecureVault", "You have unsaved changes. Discard them?")
        return True

    def clear_detail(self) -> None:
        for w in self.detail.winfo_children():
            if w is self._hero_scene:
                w.grid_remove()
            else:
                w.destroy()
        self.current_editor = None

    def _swap_detail(self, build, fade: bool = True) -> None:
        """Swap detail content directly without screenshot flicker."""
        self.clear_detail()
        build()

    def _update_selection(self) -> None:
        for item_id, row in list(self.row_widgets.items()):
            try:
                row.set_selected(item_id == self.selected_id)
            except tk.TclError:
                self.row_widgets.pop(item_id, None)

    def show_empty(self, fade: bool = True) -> None:
        self.selected_id = None
        self.in_settings = False
        if self._hero_scene is not None and self._hero_scene.winfo_ismapped():
            return

        def build():
            if self._hero_scene is None:
                self._hero_scene = HeroScene(
                    self.detail, bg=theme.CARD, title="A secure place for\nyour digital identity",
                    subtitle="Add your first account and keep every password in one encrypted vault.",
                    button=("Add account", lambda: self.open_new("account")),
                    animate=self.app.animations_enabled, radius=30)
            self._hero_scene.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        self._swap_detail(build, fade)

    def set_view(self, view: str) -> None:
        if not self.confirm_discard():
            return
        self.view = view
        self.tag_filter = None if view in VIEW_TITLES else self.tag_filter
        self.search.delete(0, "end")
        self.winfo_toplevel().focus_set()
        self._animate_rows = False
        self.show_empty()
        self._refresh_all()

    def open_new(self, kind: str = "account") -> None:
        if not self.confirm_discard():
            return
        self.selected_id = None
        self.in_settings = False

        def build():
            self.current_editor = EDITORS[kind](self.detail, self, None)
            self.current_editor.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._swap_detail(build)
        self._update_selection()
        self._refresh_sidebar()

    def open_item(self, item: Item, force: bool = False) -> None:
        if not force and (self.selected_id == item.id and self.current_editor is not None):
            return
        if not force and not self.confirm_discard():
            return
        self.selected_id = item.id
        self.in_settings = False

        def build():
            self.current_editor = EDITORS[item.kind](self.detail, self, item)
            self.current_editor.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._swap_detail(build, fade=not force)
        self._update_selection()
        self._refresh_sidebar()

    def open_settings(self, fade: bool = True) -> None:
        if fade and not self.confirm_discard():
            return
        self.selected_id = None
        self.in_settings = True

        def build():
            self.settings_panel = SettingsPanel(self.detail, self.app)
            self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self._swap_detail(build, fade)
        self._update_selection()
        self._refresh_sidebar()

    # ------------------------------------------------------------- actions
    def toast(self, text: str, error: bool = False) -> None:
        self.app.toast(text, error)

    def _copy_password(self, item: Item) -> None:
        pw = item.data.get("password", "")
        if pw:
            copy_text(self, pw, True)
            self.toast("Password copied")

    def toggle_favorite(self, item: Item) -> None:
        data = dict(item.data)
        data["favorite"] = not data.get("favorite")
        self.db.update_item(item.id, data, item.due_at)
        keep = self.current_editor
        self.reload()
        if keep is not None and self.selected_id == item.id and not keep.is_dirty():
            self.open_item(self.find(item.id), force=True)

    def save_editor(self, editor) -> None:
        problem = editor.check()
        if problem:
            self.toast(problem, error=True)
            return
        data = editor.collect()
        try:
            if editor.item:
                item_id = editor.item.id
                self.db.update_item(item_id, data, editor.due_at())
            else:
                item_id = self.db.add_item(editor.kind, data, editor.due_at())
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("SecureVault", f"Could not save:\n{exc}")
            return
        try:
            editor.attachments.commit(item_id)
        except (OSError, ValueError) as exc:
            messagebox.showerror("SecureVault", f"Account saved, but an attachment failed:\n{exc}")
        self.reload()
        saved = self.find(item_id)
        if saved:
            self.open_item(saved, force=True)
        self.toast("Saved")

    def delete_from_editor(self, editor) -> None:
        if editor.item and messagebox.askyesno(
                "SecureVault", f"Permanently delete “{editor.item.title}”? This cannot be undone."):
            self.db.delete_forever(editor.item.id)
            self.reload()
            self.show_empty()
            self.toast("Account deleted")

    # ---------------------------------------------------- state (theme change)
    def get_state(self) -> dict:
        return {"view": self.view, "tag": self.tag_filter, "selected": self.selected_id,
                "query": self.search.get()}

    def set_state(self, st: dict) -> None:
        self.view, self.tag_filter = st.get("view", "all"), st.get("tag")
        if st.get("query"):
            self.search.insert(0, st["query"])
        self._refresh_all()
        item = self.find(st["selected"]) if st.get("selected") else None
        if item:
            self.open_item(item, force=True)
