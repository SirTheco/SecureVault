"""Tests for the 2.0 hardening work.  Run with:  python -m unittest discover -s tests -v"""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vault import crypto  # noqa: E402
from vault.database import VaultDB  # noqa: E402
from vault.instance import SingleInstance  # noqa: E402
from vault.settings import DEFAULTS, Settings  # noqa: E402

crypto.SCRYPT_PARAMS["n"] = 2**10


def fresh_db(tmp: str, name: str = "vault.db") -> VaultDB:
    db = VaultDB(Path(tmp) / name)
    db.create("correct horse battery staple")
    return db


class SettingsTests(unittest.TestCase):
    def test_bad_values_fall_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"autolock_minutes": "abc", "theme": "Neon", "animations": "yes",
                                        "clipboard_clear_seconds": 99999, "unknown": 1}))
            s = Settings(path)
            self.assertEqual(s.get("autolock_minutes"), DEFAULTS["autolock_minutes"])
            self.assertEqual(s.get("theme"), "System")
            self.assertTrue(s.get("animations"))
            self.assertEqual(s.get("clipboard_clear_seconds"), 600)

    def test_non_dict_json_is_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text("[1, 2, 3]")
            self.assertEqual(Settings(path).get("autolock_minutes"), DEFAULTS["autolock_minutes"])

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            s = Settings(path)
            s.set("autolock_minutes", 15)
            self.assertEqual(Settings(path).get("autolock_minutes"), 15)


class DatabaseHardeningTests(unittest.TestCase):
    def test_async_unlock_pair(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            db.lock()
            self.assertIsNone(db.prepare_unlock("wrong password here")())
            dek = db.prepare_unlock("correct horse battery staple")()
            self.assertIsNotNone(dek)
            db.finish_unlock(dek)
            self.assertTrue(db.unlocked)

    def test_one_damaged_row_does_not_break_the_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            good = db.add_item("account", {"title": "Good", "password": "x"})
            bad = db.add_item("account", {"title": "Bad", "password": "y"})
            db.conn.execute("UPDATE items SET blob = ? WHERE id = ?", (b"garbage-bytes-garbage-bytes!", bad))
            db.conn.commit()
            items = db.get_items()
            self.assertEqual([i.id for i in items], [good])
            self.assertEqual(db.unreadable, 1)

    def test_kind_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            db.add_item("account", {"title": "A"})
            db.add_item("note", {"title": "N"})
            self.assertEqual([i.title for i in db.get_items(kind="account")], ["A"])

    def test_invalid_restore_is_rejected_and_db_stays_usable(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            db.add_item("account", {"title": "Keep me"})
            fake = Path(tmp) / "fake.db"
            con = sqlite3.connect(fake)
            con.execute("CREATE TABLE foo (x)")
            con.commit()
            con.close()
            self.assertFalse(VaultDB.is_valid_vault_file(fake))
            with self.assertRaises(ValueError):
                db.replace_with(fake)
            self.assertTrue(db.unlock("correct horse battery staple"))
            self.assertEqual(db.get_items()[0].title, "Keep me")

    def test_valid_restore_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            db.add_item("account", {"title": "Original"})
            backup = Path(tmp) / "b.db"
            db.backup_to(backup)
            self.assertTrue(VaultDB.is_valid_vault_file(backup))
            db.add_item("account", {"title": "Added later"})
            safety = db.replace_with(backup)
            self.assertTrue(safety.exists())
            self.assertTrue(db.unlock("correct horse battery staple"))
            self.assertEqual([i.title for i in db.get_items()], ["Original"])

    def test_secure_delete_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = fresh_db(tmp)
            self.assertEqual(db.conn.execute("PRAGMA secure_delete").fetchone()[0], 1)
            self.assertTrue(db.integrity_ok())


class SingleInstanceTests(unittest.TestCase):
    def test_second_instance_is_refused_and_first_is_woken(self):
        a, b = SingleInstance("unit-test-key"), SingleInstance("unit-test-key")
        woke = []
        try:
            self.assertTrue(a.acquire())
            a.serve(lambda cmd: woke.append(cmd))
            self.assertFalse(b.acquire())
            b.notify_existing()
            for _ in range(40):
                if woke:
                    break
                import time
                time.sleep(0.05)
            self.assertTrue(woke)
        finally:
            a.close()
            b.close()


class GraphicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from vault.ui import gfx  # needs customtkinter (no display required for these checks)
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"UI libraries not available: {exc}")
        cls.gfx = gfx

    def test_gradient_corners(self):
        im = self.gfx.gradient((200, 100), "#000000", "#ffffff", 62)
        self.assertEqual(im.getpixel((0, 0)), (0, 0, 0))
        self.assertGreater(im.getpixel((199, 99))[0], 250)
        top_to_bottom = self.gfx.gradient((50, 100), "#000000", "#ffffff", 90)
        self.assertLess(top_to_bottom.getpixel((25, 2))[0], 10)
        self.assertGreater(top_to_bottom.getpixel((25, 97))[0], 245)

    def test_all_sprites_and_fonts_ship(self):
        for name in ("padlock_body", "padlock_shackle", "cloud", "app_icon", "tile_cloud", "tile_key", "tile_shield",
                     "tile_card", "tile_mail", "tile_globe", "tile_user", "orb_pink", "orb_teal", "orb_orange"):
            self.assertTrue(self.gfx.asset_path("sprites", f"{name}.png").exists(), name)
        for f in self.gfx.FONT_FILES.values():
            self.assertTrue(self.gfx.asset_path("fonts", f).exists(), f)

    def test_avatar_is_square(self):
        for title in ("GitHub", "Gmail", "Zed", "", "English"):
            im = self.gfx.avatar(title, 48)
            self.assertEqual(im.size[0], im.size[1])


class SecurityCheckTests(unittest.TestCase):
    def test_find_issues(self):
        try:
            from vault.ui.main_view import find_issues
        except Exception as exc:  # noqa: BLE001
            self.skipTest(str(exc))
        import time
        from vault.database import Item
        now = time.time()

        def mk(i, pw, age_days=1):
            return Item(i, "account", {"title": f"t{i}", "password": pw}, now, now - age_days * 86400, None, None)
        issues = find_issues([mk(1, "abc123"), mk(2, "Zq!8vLw#27pXm4Rt"), mk(3, "Zq!8vLw#27pXm4Rt"),
                              mk(4, "Another-Str0ng-Pass!9", 800)])
        self.assertIn("weak", issues[1])
        self.assertIn("reused", issues[2])
        self.assertIn("reused", issues[3])
        self.assertEqual(issues[4], ["old"])


if __name__ == "__main__":
    unittest.main()


class AnimationTests(unittest.TestCase):
    def test_tween_runs_immediately_when_animations_are_off(self):
        try:
            from vault.ui import anim
        except Exception as exc:  # noqa: BLE001
            self.skipTest(str(exc))
        anim.init(None, lambda: False)
        seen = []
        anim.start("t", 300, seen.append, done=lambda: seen.append("done"))
        self.assertEqual(seen, [1.0, "done"])

    def test_easings_hit_their_endpoints(self):
        try:
            from vault.ui import anim
        except Exception as exc:  # noqa: BLE001
            self.skipTest(str(exc))
        for fn in (anim.ease_out, anim.ease_in_out, anim.ease_out_back, anim.linear):
            self.assertAlmostEqual(fn(0.0), 0.0, places=6)
            self.assertAlmostEqual(fn(1.0), 1.0, places=6)

    def test_with_alpha_scales_opacity(self):
        try:
            from PIL import Image
            from vault.ui import anim
        except Exception as exc:  # noqa: BLE001
            self.skipTest(str(exc))
        img = Image.new("RGBA", (4, 4), (10, 20, 30, 200))
        self.assertEqual(anim.with_alpha(img, 0.5).getpixel((0, 0))[3], 100)
        self.assertEqual(anim.with_alpha(img, 1.0).getpixel((0, 0))[3], 200)


class ScrollFixTests(unittest.TestCase):
    def test_scroll_frames_use_per_pixel_steps_and_reach_the_bottom(self):
        try:
            import customtkinter as ctk
            from vault.ui import anim
            root = ctk.CTk()
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"no display / UI libs: {exc}")
        try:
            anim.init(root, lambda: False)       # animations off -> scroll_notches jumps straight to the end
            frame = anim.SmoothScrollFrame(root, width=300, height=200)
            frame.pack()
            for i in range(30):
                ctk.CTkLabel(frame, text=f"row {i}").pack(pady=3)
            root.update()
            self.assertEqual(int(frame._parent_canvas.cget("yscrollincrement")), 1)
            frame.scroll_notches(200)
            root.update()
            self.assertAlmostEqual(frame._parent_canvas.yview()[1], 1.0, places=3)
            frame.scroll_notches(-200)
            root.update()
            self.assertAlmostEqual(frame._parent_canvas.yview()[0], 0.0, places=3)
        finally:
            root.destroy()


class QuitCommandTests(unittest.TestCase):
    def test_quit_and_open_commands_reach_the_running_instance(self):
        import time
        a, b = SingleInstance("unit-test-quit-key"), SingleInstance("unit-test-quit-key")
        seen = []
        try:
            self.assertTrue(a.acquire())
            a.serve(seen.append)
            self.assertTrue(b.notify_existing("open"))
            self.assertTrue(b.notify_existing("quit"))
            for _ in range(40):
                if len(seen) >= 2:
                    break
                time.sleep(0.05)
            self.assertEqual(seen, ["open", "quit"])
        finally:
            a.close()
            b.close()

    def test_notify_without_a_running_instance_returns_false(self):
        self.assertFalse(SingleInstance("nobody-is-home-key").notify_existing("quit"))


