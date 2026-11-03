"""Caps warning and persistent hero regression tests."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch


class CapsHintTests(unittest.TestCase):
    def test_hint_tracks_focus_and_caps_without_replacing_bindings(self):
        try:
            from vault.ui import capslock
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")

        class Label:
            def __init__(self, *args, **kwargs):
                self.visible = False

            def grid(self, **kwargs):
                self.visible = True

            def grid_remove(self):
                self.visible = False

        class Entry:
            def __init__(self):
                self.handlers = {}
                self.jobs = {}
                self.counter = 0

            def bind(self, event, callback, add=None):
                assert add == "+"
                self.handlers[event] = callback

            def after(self, delay, callback):
                self.counter += 1
                self.jobs[self.counter] = callback
                return self.counter

            def after_cancel(self, job):
                self.jobs.pop(job, None)

        entry = Entry()
        with patch.object(capslock.ctk, "CTkLabel", Label), \
             patch.object(capslock.theme, "font", return_value=None), \
             patch.object(capslock.sys, "platform", "win32"), \
             patch.object(capslock, "_windows_caps_lock", return_value=True) as caps:
            hint = capslock.attach_caps_hint(entry, object(), 1)
            self.assertFalse(hint.visible)
            entry.handlers["<FocusIn>"](None)
            self.assertTrue(hint.visible)
            self.assertEqual(len(entry.jobs), 1)
            caps.return_value = False
            entry.handlers["<KeyPress>"](SimpleNamespace())
            self.assertFalse(hint.visible)
            self.assertEqual(len(entry.jobs), 1)
            caps.return_value = True
            entry.handlers["<KeyPress>"](SimpleNamespace())
            self.assertTrue(hint.visible)
            entry.handlers["<FocusOut>"](None)
            self.assertFalse(hint.visible)
            self.assertFalse(entry.jobs)


class PersistentHeroTests(unittest.TestCase):
    def test_navigation_reuses_hero_and_does_not_crossfade(self):
        try:
            from vault.ui.main_view import MainView
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")

        class FakeHero:
            def __init__(self, detail, **kwargs):
                self.mapped = False
                self.removed = 0
                detail.children.append(self)

            def grid(self, **kwargs):
                self.mapped = True

            def grid_remove(self):
                self.mapped = False
                self.removed += 1

            def winfo_ismapped(self):
                return self.mapped

        class Detail:
            def __init__(self):
                self.children = []

            def winfo_children(self):
                return list(self.children)

        scene = SimpleNamespace(detail=Detail(), _hero_scene=None, selected_id=1,
                                in_settings=True, current_editor=None,
                                app=SimpleNamespace(animations_enabled=lambda: True),
                                open_new=lambda kind: None)
        scene.clear_detail = lambda: MainView.clear_detail(scene)
        scene._swap_detail = lambda build, fade=True: MainView._swap_detail(scene, build, fade)
        with patch("vault.ui.main_view.HeroScene", FakeHero), \
             patch("vault.ui.main_view.anim.crossfade") as crossfade:
            MainView.show_empty(scene)
            hero = scene._hero_scene
            MainView.show_empty(scene)
            self.assertEqual(hero.removed, 0)
            scene.clear_detail()
            MainView.show_empty(scene)
            self.assertIs(scene._hero_scene, hero)
            self.assertEqual(hero.removed, 2)
            self.assertTrue(hero.mapped)
            crossfade.assert_not_called()


if __name__ == "__main__":
    unittest.main()
