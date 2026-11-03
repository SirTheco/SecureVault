"""Regression tests for per-account icon colors and encrypted persistence."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PIL import ImageChops, ImageStat


class AccountIconColorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from vault.ui import editors, gfx
        except ImportError as exc:
            raise unittest.SkipTest(f"UI dependencies unavailable: {exc}")
        cls.gfx, cls.editors = gfx, editors

    def test_automatic_icons_and_invalid_values_are_unchanged(self):
        for title in ("Zebra", "Gmail", "Bank", "VPN", "Security", "website"):
            automatic = self.gfx.avatar(title, 48)
            for invalid in ("", None, "red", "#123", "#GG1234", {"bad": 1}):
                self.assertEqual(automatic.tobytes(), self.gfx.avatar(title, 48, invalid).tobytes())

    def test_letter_and_all_picture_categories_accept_colors(self):
        for title in ("Zebra", "Gmail", "Bank", "VPN", "Security", "website", "cloud", "user"):
            automatic = self.gfx.avatar(title, 64)
            red = self.gfx.avatar(title, 64, "#F02020")
            blue = self.gfx.avatar(title, 64, "#2050F0")
            black = self.gfx.avatar(title, 64, "#000000")
            white = self.gfx.avatar(title, 64, "#FFFFFF")
            for image in (red, blue, black, white):
                self.assertEqual(image.size, automatic.size)
                self.assertIsNotNone(ImageChops.difference(image.convert("RGB"), automatic.convert("RGB")).getbbox(), title)
                self.assertEqual(image.getchannel("A").tobytes(), automatic.getchannel("A").tobytes())
            self.assertIsNotNone(ImageChops.difference(red.convert("RGB"), blue.convert("RGB")).getbbox(), title)
            self.assertGreater(ImageStat.Stat(white.convert("RGB")).mean[0],
                               ImageStat.Stat(black.convert("RGB")).mean[0], title)

    def test_sprite_override_is_independent_of_theme(self):
        with mock.patch.object(self.gfx, "_sprite_raw", side_effect=AssertionError("theme used")):
            self.gfx._avatar.cache_clear()
            self.gfx.avatar("Gmail", 64, "#AA1234")

    def test_editor_choose_cancel_reset_preview_and_save(self):
        editor = object.__new__(self.editors.AccountEditor)
        value = lambda v: SimpleNamespace(get=lambda *args: v)
        editor.item = SimpleNamespace(data={"title": "Gmail", "password": "secret",
                                            "title_color": "#123456", "extra": "keep"})
        editor.title_entry = value("Gmail renamed")
        editor.username = value("user")
        editor.password = value("secret")
        editor.url = value("site")
        editor.tags_entry = value("work")
        editor.notes = value("private notes")
        editor.cf_rows = []
        editor.favorite = True
        editor.title_color = "#123456"
        editor.icon_color = ""
        editor._icon_color_changed = False
        editor.header = SimpleNamespace(update_content=mock.Mock())
        with mock.patch.object(self.editors.colorchooser, "askcolor", return_value=(None, "#ff0000")):
            editor._choose_icon_color()
        editor.header.update_content.assert_called_with("Gmail renamed", "user", True, "#123456", "#FF0000")
        data = editor.collect()
        self.assertEqual(data["icon_color"], "#FF0000")
        self.assertEqual(data["title_color"], "#123456")
        self.assertEqual(data["extra"], "keep")
        with mock.patch.object(self.editors.colorchooser, "askcolor", return_value=(None, None)):
            editor._choose_icon_color()
        self.assertEqual(editor.icon_color, "#FF0000")
        editor.item = SimpleNamespace(data=data)
        editor._icon_color_changed = False
        self.assertEqual(editor.collect()["icon_color"], "#FF0000")
        editor._reset_icon_color()
        self.assertNotIn("icon_color", editor.collect())
        editor.header.update_content.assert_called_with("Gmail renamed", "user", True, "#123456", "")

    def test_encrypted_storage_rename_and_reset(self):
        from vault.database import VaultDB
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vault.db"
            db = VaultDB(path)
            db.create("a strong test password")
            first = db.add_item("account", {"title": "Gmail", "password": "secret",
                                            "icon_color": "#BE43A7", "extra": "unchanged"})
            db.add_item("account", {"title": "Other", "icon_color": "#09F012"})
            items = {i.id: i for i in db.get_items()}
            data = dict(items[first].data)
            data["title"] = "Zebra"
            db.update_item(first, data)
            db.lock()
            self.assertTrue(db.unlock("a strong test password"))
            items = {i.id: i for i in db.get_items()}
            self.assertEqual(items[first].data["icon_color"], "#BE43A7")
            self.assertEqual(items[first].data["password"], "secret")
            self.assertEqual(items[first].data["extra"], "unchanged")
            self.assertEqual(next(i for i in items.values() if i.id != first).data["icon_color"], "#09F012")
            data = dict(items[first].data)
            data.pop("icon_color")
            db.update_item(first, data)
            self.assertNotIn("icon_color", next(i for i in db.get_items() if i.id == first).data)
            db.close()
            self.assertNotIn(b"#BE43A7", path.read_bytes())

    def test_list_and_header_render_override_without_changing_title(self):
        import tkinter as tk
        from vault.ui.rows import AccountRow
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Display unavailable: {exc}")
        try:
            root.geometry("700x400")
            item = SimpleNamespace(title="Gmail", data={"icon_color": "#FF2200",
                                                       "title_color": "#112233"})
            with mock.patch.object(self.gfx, "avatar", wraps=self.gfx.avatar) as render:
                row = AccountRow(root, item, "user", False, [], lambda: None, lambda: None, lambda: None)
                row.pack(fill="x")
                header = self.editors.HeaderCard(root, [])
                header.pack(fill="x")
                root.update()
                header.update_content("Gmail", "user", False, "#112233", "#FF2200")
                self.assertIn(mock.call("Gmail", 48, "#FF2200"), render.call_args_list)
                self.assertIn(mock.call("Gmail", 76, "#FF2200"), render.call_args_list)
                self.assertEqual(row.itemcget(row._ids["title"], "fill").lower(), "#112233")
                title_id = next(i for i in header.find_all()
                                if header.type(i) == "text" and header.itemcget(i, "text") == "Gmail")
                self.assertEqual(header.itemcget(title_id, "fill").lower(), "#112233")
                header.update_content("Gmail", "user", False, "#112233", "")
                self.assertEqual(header.itemcget(
                    next(i for i in header.find_all() if header.type(i) == "text"
                         and header.itemcget(i, "text") == "Gmail"), "fill").lower(), "#112233")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
