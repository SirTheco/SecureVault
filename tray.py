"""Account editor shown in the detail panel (header card + form)."""
from __future__ import annotations

import json
import os
import re
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox

import customtkinter as ctk
from ..database import MAX_ATTACHMENT_BYTES
from ..utils import fmt_ts, human_size
from . import anim, gfx, theme
from .capslock import attach_caps_hint
from .dialogs import PasswordGeneratorDialog
from .gfx import S
from .theme import pick
from .widgets import GButton, IconButton, SecretEntry, StrengthMeter, copy_text, entry


def _label(parent, text):
    return ctk.CTkLabel(parent, text=text, font=theme.font(12, "medium"), text_color=theme.MUTED, anchor="w")


class HeaderCard(tk.Canvas):
    """Purple gradient card with a live avatar/title preview and quick actions."""

    H = 128

    def __init__(self, master, actions):
        super().__init__(master, height=S(self.H), bg=pick(theme.CARD), highlightthickness=0, bd=0)
        self.actions = actions            # list of (key, icon, tooltip, callback)
        self.title, self.subtitle, self.fav, self.title_color, self.icon_color = "", "", False, "", ""
        self._cw = 0
        self._keep: list = []
        self._zones: list = []
        self._hover = None
        self.f_title = gfx.tkfont_for(22, "bold")
        self.f_sub = gfx.tkfont_for(12)
        self.bind("<Configure>", lambda e: self.redraw() if e.width != self._cw else None)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda _e: self._set_hover(None))
        self.bind("<ButtonRelease-1>", self._click)

    def update_content(self, title: str, subtitle: str, fav: bool, title_color: str = "", icon_color: str = ""):
        if (title, subtitle, fav, title_color, icon_color) != (self.title, self.subtitle, self.fav, self.title_color, self.icon_color):
            self.title, self.subtitle, self.fav, self.title_color, self.icon_color = title, subtitle, fav, title_color, icon_color
            self.redraw()

    def redraw(self):
        w = self.winfo_width()
        if w < 60:
            return
        self._cw = w
        h = S(self.H)
        for ph in self._keep:
            gfx.release(ph)
        self._keep.clear()
        self._zones.clear()
        self.delete("all")

        def keep(img):
            ph = gfx.photo(img)
            self._keep.append(ph)
            return ph
        panel = gfx.panel_image(w, h, "#7B55EC" if not theme.dark() else "#5B3FD0",
                                "#A98CFF" if not theme.dark() else "#7A5EEB", S(28), angle=20)
        self.create_image(0, 0, anchor="nw", image=keep(panel))
        name = self.title.strip() or "New account"
        self.create_image(S(22), h // 2, anchor="w", image=keep(gfx.avatar(name, 76, self.icon_color)))
        right = w - S(18)
        for key, icon, tip, cb in reversed(self.actions):
            active = key == "fav" and self.fav
            ic_name = "star_fill" if active else icon
            size = S(40)
            cx = right - size // 2
            if self._hover == key:
                disc = gfx.card_image(size, size, "#FFFFFF", size // 2, None)
                disc.putalpha(disc.getchannel("A").point(lambda v: int(v * 0.30)))
                self.create_image(cx, h // 2, image=keep(disc))
            col = "#FFD36B" if active else "#FFFFFF"
            self.create_image(cx, h // 2, image=keep(gfx.icon(ic_name, 20, col)))
            self._zones.append((key, cx - size // 2, 0, cx + size // 2, h, cb))
            right -= size + S(4)
        text_x = S(22) + S(76) + S(18)
        room = right - text_x
        from .rows import ellipsize
        self.create_text(text_x, h // 2 - S(12), anchor="w", text=ellipsize(self.f_title, name, room),
                         fill=self.title_color or "#FFFFFF", font=self.f_title)
        self.create_text(text_x, h // 2 + S(17), anchor="w",
                         text=ellipsize(self.f_sub, self.subtitle or "Fill in the details below", room),
                         fill="#EDE6FF", font=self.f_sub)

    def _at(self, x, y):
        for z in self._zones:
            if z[1] <= x <= z[3] and z[2] <= y <= z[4]:
                return z
        return None

    def _motion(self, e):
        z = self._at(e.x, e.y)
        self._set_hover(z[0] if z else None)

    def _set_hover(self, key):
        if key != self._hover:
            self._hover = key
            self.configure(cursor="hand2" if key else "arrow")
            self.redraw()

    def _click(self, e):
        z = self._at(e.x, e.y)
        if z:
            z[5]()

    def destroy(self):
        for ph in self._keep:
            gfx.release(ph)
        super().destroy()


class AttachmentsPanel(ctk.CTkFrame):
    """Encrypted file attachments. Files added to an unsaved item are held until Save."""

    def __init__(self, master, db, get_item_id):
        super().__init__(master, fg_color="transparent")
        self.db, self.get_item_id = db, get_item_id
        self.pending: list[str] = []
        self.columnconfigure(0, weight=1)
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(head, text="Attachments (stored encrypted)", font=theme.font(12, "medium"),
                     text_color=theme.MUTED, anchor="w").pack(side="left")
        GButton(head, "Attach file", self.add, width=116, height=32, style="soft", icon="plus", size=12,
                bg=theme.CARD).pack(side="right")
        self.rows = ctk.CTkFrame(self, fg_color="transparent")
        self.rows.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.rows.columnconfigure(0, weight=1)
        self.refresh()

    def refresh(self) -> None:
        for w in self.rows.winfo_children():
            w.destroy()
        item_id = self.get_item_id()
        saved = self.db.list_attachments(item_id) if item_id else []
        r = 0
        for att in saved:
            ctk.CTkLabel(self.rows, text=f"{att['name']}  ({human_size(att['size'])})", font=theme.font(12),
                         text_color=theme.TEXT, anchor="w").grid(row=r, column=0, sticky="ew", pady=3)
            IconButton(self.rows, "download", lambda a=att: self.export(a), size=32, tooltip="Export").grid(row=r, column=1)
            IconButton(self.rows, "trash", lambda a=att: self.delete(a), size=32, color=theme.DANGER,
                       hover_color=theme.DANGER, tooltip="Delete").grid(row=r, column=2)
            r += 1
        for path in self.pending:
            ctk.CTkLabel(self.rows, text=f"{os.path.basename(path)}  (encrypted when you press Save)",
                         font=theme.font(12), text_color=theme.TEXT, anchor="w").grid(row=r, column=0, sticky="ew", pady=3)
            IconButton(self.rows, "x", lambda p=path: self._unpend(p), size=32, tooltip="Remove").grid(row=r, column=1)
            r += 1
        if r == 0:
            ctk.CTkLabel(self.rows, text="No files attached.", font=theme.font(12), text_color=theme.MUTED,
                         anchor="w").grid(row=0, column=0, sticky="w")

    def _unpend(self, path: str) -> None:
        self.pending.remove(path)
        self.refresh()

    def add(self) -> None:
        paths = filedialog.askopenfilenames(parent=self.winfo_toplevel(), title="Choose files to attach")
        item_id = self.get_item_id()
        for path in paths:
            try:
                if os.path.getsize(path) > MAX_ATTACHMENT_BYTES:
                    messagebox.showwarning("SecureVault", f"{os.path.basename(path)} is larger than 50 MB.")
                    continue
                if item_id:
                    self.db.add_attachment(item_id, path)
                else:
                    self.pending.append(path)
            except (OSError, ValueError) as exc:
                messagebox.showerror("SecureVault", f"Could not attach the file:\n{exc}")
        self.refresh()

    def commit(self, item_id: int) -> None:
        for path in list(self.pending):
            self.db.add_attachment(item_id, path)
            self.pending.remove(path)

    def export(self, att: dict) -> None:
        dest = filedialog.asksaveasfilename(parent=self.winfo_toplevel(), initialfile=att["name"])
        if dest:
            try:
                self.db.export_attachment(att["id"], dest)
            except OSError as exc:
                messagebox.showerror("SecureVault", f"Could not export the file:\n{exc}")
                return
            messagebox.showinfo("SecureVault", "Exported. Note: the exported copy is NOT encrypted.")

    def delete(self, att: dict) -> None:
        if messagebox.askyesno("SecureVault", f"Delete attachment '{att['name']}'?"):
            self.db.delete_attachment(att["id"])
            self.refresh()


class AccountEditor(ctk.CTkFrame):
    kind = "account"

    def __init__(self, master, host, item=None):
        super().__init__(master, fg_color="transparent")
        self.host, self.item = host, item
        self.favorite = bool(item.data.get("favorite")) if item else False
        self.title_color = item.data.get("title_color", "") if item else ""
        if not isinstance(self.title_color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", self.title_color):
            self.title_color = ""
        self.icon_color = gfx.valid_avatar_color(item.data.get("icon_color", "")) if item else ""
        self._icon_color_changed = False
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.header = HeaderCard(self, [
            ("fav", "star", "Favorite", self._toggle_fav),
            ("user", "user", "Copy username", lambda: copy_text(self, self.username.get())),
            ("pass", "copy", "Copy password", lambda: copy_text(self, self.password.get(), True)),
            ("open", "open", "Open website", self._open_url),
        ])
        self.header.grid(row=0, column=0, sticky="ew", padx=22, pady=(22, 6))

        self.body = anim.SmoothScrollFrame(self, fg_color="transparent", scrollbar_button_color=theme.BORDER,
                                           scrollbar_button_hover_color=theme.PRIMARY)
        self.body.grid(row=1, column=0, sticky="nsew", padx=(10, 6), pady=(0, 0))
        self.body.columnconfigure(0, weight=1)
        self.row = 0
        self.title_entry = self.field("Title *", entry(self.body, "e.g. GitHub"))
        self.title_entry.bind("<KeyRelease>", lambda _e: self._refresh_header())
        color_controls = ctk.CTkFrame(self.body, fg_color="transparent")
        GButton(color_controls, "Choose color", self._choose_title_color, width=150, height=36,
                style="soft", size=12, bg=theme.CARD).pack(side="left")
        GButton(color_controls, "Reset", self._reset_title_color, width=84, height=36,
                style="soft", size=12, bg=theme.CARD).pack(side="left", padx=8)
        self.field("Title color", color_controls, pady=(8, 0))
        icon_controls = ctk.CTkFrame(self.body, fg_color="transparent")
        GButton(icon_controls, "Choose color", self._choose_icon_color, width=150, height=36,
                style="soft", size=12, bg=theme.CARD).pack(side="left")
        GButton(icon_controls, "Reset", self._reset_icon_color, width=84, height=36,
                style="soft", size=12, bg=theme.CARD).pack(side="left", padx=8)
        self.field("Icon color", icon_controls, pady=(8, 0))
        self.username = self.field("Username / Email", entry(self.body, "name@example.com"))
        self.username.bind("<KeyRelease>", lambda _e: self._refresh_header())
        self.password = SecretEntry(self.body, on_change=self._pw_changed, on_generate=self._open_generator, bg=theme.CARD)
        self.field("Password", self.password)
        self.meter = StrengthMeter(self.body, width=420)
        self.field(None, self.meter, pady=(6, 0))
        self.url = self.field("Website", entry(self.body, "example.com"))
        self.url.bind("<KeyRelease>", lambda _e: self._refresh_header())
        self.tags_entry = self.field("Tags (comma separated)", entry(self.body, "work, social, finance"))
        self.notes = self.field("Notes", ctk.CTkTextbox(self.body, height=96, wrap="word", corner_radius=14,
                                                       fg_color=theme.INPUT, border_color=theme.BORDER, border_width=1,
                                                       text_color=theme.TEXT, font=theme.font(13)))

        self._wire_notes_wheel()

        head = ctk.CTkFrame(self.body, fg_color="transparent")
        ctk.CTkLabel(head, text="Custom fields (security questions, card info, PINs…)", font=theme.font(12, "medium"),
                     text_color=theme.MUTED, anchor="w").pack(side="left")
        GButton(head, "Add field", self.add_custom_row, width=106, height=32, style="soft", icon="plus", size=12,
                bg=theme.CARD).pack(side="right")
        self.field(None, head, pady=(18, 0))
        self.cf_frame = ctk.CTkFrame(self.body, fg_color="transparent", height=2)
        self.cf_frame.columnconfigure(0, weight=1)
        self.field(None, self.cf_frame, pady=(4, 0))
        self.cf_rows: list[dict] = []

        self.attachments = AttachmentsPanel(self.body, host.db, lambda: self.item.id if self.item else None)
        self.field(None, self.attachments, pady=(18, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=22, pady=(6, 20))
        footer.columnconfigure(1, weight=1)
        GButton(footer, "Save changes", lambda: host.save_editor(self), width=170, height=48, icon="check").grid(
            row=0, column=0)
        self.status = ctk.CTkLabel(footer, text="", font=theme.font(11), text_color=theme.MUTED, anchor="w")
        self.status.grid(row=0, column=1, sticky="ew", padx=14)
        if item:
            GButton(footer, "Delete", lambda: host.delete_from_editor(self), width=118, height=44, style="outline",
                    icon="trash", size=12).grid(row=0, column=2)
            self.status.configure(text=f"Updated {fmt_ts(item.updated_at)}")

        if item:
            d = item.data
            self.title_entry.insert(0, d.get("title", ""))
            self.username.insert(0, d.get("username", ""))
            self.password.set(d.get("password", ""))
            self.url.insert(0, d.get("url", ""))
            self.tags_entry.insert(0, ", ".join(d.get("tags", [])))
            self.notes.insert("1.0", d.get("notes", ""))
            for f in d.get("fields", []):
                self.add_custom_row(f.get("label", ""), f.get("value", ""), f.get("secret", False))
        self._pw_changed()
        self.snapshot = self._dump()
        self.after(60, self._refresh_header)
        if not item:
            self.after(200, self.title_entry.focus_set)

    # --------------------------------------------------------------- helpers
    def _wire_notes_wheel(self) -> None:
        """A text box swallows mouse-wheel events, which used to trap the page scroll. Scroll the note while it
        has more text in that direction, otherwise hand the wheel to the page."""
        text = self.notes._textbox

        def on_wheel(event):
            if getattr(event, "num", 0) == 4:
                step = -1
            elif getattr(event, "num", 0) == 5:
                step = 1
            else:
                step = -1 if event.delta > 0 else 1
            first, last = text.yview()
            if (step > 0 and last < 1.0) or (step < 0 and first > 0.0):
                text.yview_scroll(step, "units")
            else:
                self.body.scroll_notches(step)
            return "break"
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            text.bind(seq, on_wheel)

    def field(self, label, widget, pady=(12, 0)):
        if label:
            _label(self.body, label).grid(row=self.row, column=0, sticky="ew", padx=12, pady=pady)
            self.row += 1
            pady = (3, 0)
        widget.grid(row=self.row, column=0, sticky="ew", padx=12, pady=pady)
        self.row += 1
        if isinstance(widget, (ctk.CTkEntry, ctk.CTkTextbox)):
            attach_caps_hint(widget, self.body, self.row, padx=12, pady=(2, 0))
            self.row += 1
        return widget

    def _refresh_header(self):
        sub = self.username.get().strip() or self.url.get().strip()
        self.header.update_content(self.title_entry.get(), sub, self.favorite, self.title_color, self.icon_color)

    def _choose_icon_color(self):
        _, selected = colorchooser.askcolor(color=self.icon_color or "#8067C4", parent=self,
                                            title="Choose account icon color")
        if selected:
            self.icon_color = gfx.valid_avatar_color(selected)
            self._icon_color_changed = True
            self._refresh_header()

    def _reset_icon_color(self):
        self.icon_color = ""
        self._icon_color_changed = True
        self._refresh_header()

    def _choose_title_color(self):
        _, selected = colorchooser.askcolor(color=self.title_color or "#FFFFFF", parent=self,
                                            title="Choose account title color")
        if selected:
            self.title_color = selected
            self._refresh_header()

    def _reset_title_color(self):
        self.title_color = ""
        self._refresh_header()

    def _toggle_fav(self):
        self.favorite = not self.favorite
        self._refresh_header()

    def _pw_changed(self):
        self.meter.update_for(self.password.get())

    def _open_generator(self):
        def use(pw):
            self.password.set(pw)
            self._pw_changed()
        PasswordGeneratorDialog(self.winfo_toplevel(), use)

    def _open_url(self):
        url = self.url.get().strip()
        if url:
            webbrowser.open(url if url.lower().startswith(("http://", "https://")) else "https://" + url)

    def add_custom_row(self, label: str = "", value: str = "", secret: bool = False) -> None:
        frame = ctk.CTkFrame(self.cf_frame, fg_color="transparent")
        frame.columnconfigure(1, weight=1)
        frame.pack(fill="x", pady=3)
        lab = entry(frame, "Label", width=140)
        lab.grid(row=0, column=0)
        val = entry(frame, "Value")
        val.grid(row=0, column=1, sticky="ew", padx=6)
        attach_caps_hint(lab, frame, row=1, column=0, pady=(2, 0))
        attach_caps_hint(val, frame, row=1, column=1, padx=6, pady=(2, 0))
        var = ctk.BooleanVar(value=secret)
        if label:
            lab.insert(0, label)
        if value:
            val.insert(0, value)
        val.configure(show="•" if secret else "")
        ctk.CTkCheckBox(frame, text="Hide", variable=var, width=60, font=theme.font(12), text_color=theme.TEXT,
                        fg_color=theme.PRIMARY, hover_color=theme.PRIMARY_HOVER, border_color=theme.BORDER,
                        corner_radius=8, checkbox_width=20, checkbox_height=20,
                        command=lambda: val.configure(show="•" if var.get() else "")).grid(row=0, column=2)
        IconButton(frame, "copy", lambda: copy_text(self, val.get(), bool(var.get())), size=34, tooltip="Copy").grid(
            row=0, column=3, padx=(4, 0))
        row = {"frame": frame, "label": lab, "value": val, "secret": var}
        IconButton(frame, "x", lambda: self._remove_row(row), size=34, color=theme.DANGER, hover_color=theme.DANGER,
                   tooltip="Remove").grid(row=0, column=4)
        self.cf_rows.append(row)

    def _remove_row(self, row: dict) -> None:
        row["frame"].destroy()
        self.cf_rows.remove(row)

    # ------------------------------------------------------------ data flow
    def collect(self) -> dict:
        fields = []
        for r in self.cf_rows:
            label, value = r["label"].get().strip(), r["value"].get()
            if label or value:
                fields.append({"label": label, "value": value, "secret": bool(r["secret"].get())})
        data = dict(self.item.data) if self.item else {}
        data.update({
            "title": self.title_entry.get().strip(),
            "tags": [t.strip() for t in self.tags_entry.get().split(",") if t.strip()],
            "username": self.username.get().strip(),
            "password": self.password.get(),
            "url": self.url.get().strip(),
            "notes": self.notes.get("1.0", "end-1c"),
            "fields": fields,
            "favorite": self.favorite,
            "title_color": self.title_color,
        })
        if self._icon_color_changed:
            if self.icon_color:
                data["icon_color"] = self.icon_color
            else:
                data.pop("icon_color", None)
        return data

    def due_at(self):
        return None

    def _dump(self) -> str:
        return json.dumps(self.collect(), sort_keys=True)

    def is_dirty(self) -> bool:
        return self._dump() != self.snapshot

    def check(self) -> str | None:
        if not self.title_entry.get().strip():
            return "Please enter a title."
        return None


EDITORS = {"account": AccountEditor}
