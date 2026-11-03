"""Regression coverage for appearance changes initiated from Settings."""
import os
import tempfile
import time
import unittest
from unittest import mock


class ThemeChangeTests(unittest.TestCase):
    def test_theme_and_palette_clicks_preserve_vault_and_settings_view(self):
        try:
            import tkinter as tk
            import customtkinter
            from vault.ui.app import VaultApp
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.dict(os.environ, {"SECUREVAULT_HOME": folder}), \
             mock.patch("vault.ui.app.Tray.start"):
            try:
                app = VaultApp()
            except tk.TclError as exc:
                self.skipTest(f"Display unavailable: {exc}")
            errors = []
            app.report_callback_exception = lambda exc, val, tb: errors.append((exc, val))

            def pump(seconds):
                end = time.monotonic() + seconds
                while time.monotonic() < end:
                    app.update()
                    time.sleep(0.005)

            def click(chip):
                chip.event_generate("<Enter>")
                chip.event_generate("<ButtonPress-1>", x=8, y=8)
                pump(0.09)
                chip.event_generate("<ButtonRelease-1>", x=8, y=8)
                pump(0.3)

            try:
                app.db.create("a temporary test password")
                app.db.add_item("account", {"title": "Example", "username": "test",
                                            "password": "test secret", "tags": []})
                app.on_unlocked()
                pump(0.7)
                app.main.search.insert(0, "Example")
                app.main._refresh_all()
                app.main.open_settings(fade=False)
                pump(0.2)
                for enabled in (True, False):
                    app.settings.set("animations", enabled)
                    for mode in ("Dark", "Light", "System"):
                        click(dict(app.main.settings_panel._chips)[mode])
                        self.assertEqual(app.settings.get("theme"), mode)
                        self.assertTrue(app.main.in_settings)
                        self.assertEqual(app.main.search.get(), "Example")
                        self.assertEqual(app.db.get_items(kind="account")[0].data["password"], "test secret")
                    click(dict(app.main.settings_panel._palette_chips)["Ocean"])
                    self.assertEqual(app.settings.get("palette"), "Ocean")
                self.assertFalse(errors, errors)
            finally:
                # This test creates and tears down a root in the same process as
                # other Tk tests. Don't leave Tcl timer callbacks behind.
                for job in app.tk.call("after", "info"):
                    app.after_cancel(job)
                app.quit_app()


if __name__ == "__main__":
    unittest.main()
