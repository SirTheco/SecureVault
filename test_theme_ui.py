"""Regression checks for the redesigned artwork's gentle motion."""
import unittest
from unittest.mock import patch


class SceneMotionTests(unittest.TestCase):
    def test_icons_float_slowly_without_moving_the_lock(self):
        try:
            from vault.ui.scene import HeroScene
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")

        class SceneStub:
            def __init__(self):
                self._open = None
                self._sparks = []
                self._items = [
                    dict(name="icon", item=1, kind="tile", x=100, y=100, phase=0.3),
                    dict(name="body", item=2, kind="pad", x=150, y=150, phase=0),
                ]
                self.positions = {}
                self.enabled = True

            def animate(self):
                return self.enabled

            def _icons_on(self):
                return False

            def coords(self, item, x, y):
                self.positions[item] = (x, y)

        scene = SceneStub()
        with patch("vault.ui.scene.anim.enabled", return_value=True), \
             patch("vault.ui.scene.gfx.scale", return_value=1):
            HeroScene._apply(scene, 0)
            initial = dict(scene.positions)
            HeroScene._apply(scene, 2)
            self.assertNotEqual(scene.positions[1], initial[1])
            self.assertEqual(scene.positions[2], initial[2])
            self.assertLess(abs(scene.positions[1][1] - initial[1][1]), 4)
            scene.enabled = False
            HeroScene._apply(scene, 2)
            self.assertEqual(scene.positions, initial)

    def test_unlock_finishes_once_at_faster_duration(self):
        try:
            from PIL import Image
            from vault.ui.scene import HeroScene, UNLOCK_SECONDS, UNLOCK_PAUSE_MS, UNLOCK_ANGLE, unlock_pose
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")

        class SceneStub:
            def __init__(self):
                self._open = [10.0, lambda: self.calls.append("done"), False]
                self._items = [dict(name="shackle", item=1, x=20, y=30)]
                self._arch_image = Image.new("RGBA", (10, 10))
                self._arch_pivot = (5, 5)
                self._arch_center_offset = (0, 0)
                self._arch_height = 10
                self._lift_padding = 4
                self._open_frame_angle = None
                self._open_frame_lift = None
                self._open_frame_ph = None
                self._photos = []
                self.calls = []
                self.jobs = []
            def _keep(self, img):
                photo = object()
                self._photos.append(photo)
                return photo
            def itemconfigure(self, *args, **kwargs):
                pass
            def coords(self, *args):
                pass
            def after(self, delay, callback):
                self.jobs.append((delay, callback))
                return "job"

        scene = SceneStub()
        self.assertLess(UNLOCK_SECONDS, 1.35)
        self.assertEqual(UNLOCK_PAUSE_MS, 500)
        with patch("vault.ui.scene.time.monotonic", return_value=10.0 + UNLOCK_SECONDS / 2), \
             patch("vault.ui.scene.gfx.release"), patch("vault.ui.scene.gfx.scale", return_value=1):
            HeroScene._step_open(scene)
            self.assertEqual(scene._open_frame_angle, round(unlock_pose(0.5)[0], 2))
            self.assertFalse(scene.jobs)
        with patch("vault.ui.scene.time.monotonic", return_value=10.0 + UNLOCK_SECONDS + 0.01), \
             patch("vault.ui.scene.gfx.release"), patch("vault.ui.scene.gfx.scale", return_value=1):
            HeroScene._step_open(scene)
            HeroScene._step_open(scene)
            self.assertEqual(scene._open_frame_angle, UNLOCK_ANGLE)
            self.assertEqual(len(scene.jobs), 1)
            self.assertEqual(scene.jobs[0][0], UNLOCK_PAUSE_MS)
            scene.jobs[0][1]()
            self.assertEqual(scene.calls, ["done"])

    def test_unlock_pose_is_smooth_and_never_reverses(self):
        try:
            from vault.ui.scene import unlock_pose, UNLOCK_ANGLE, UNLOCK_LIFT
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        poses = [unlock_pose(i / 1000) for i in range(1001)]
        self.assertEqual(poses[0], (0.0, 0.0))
        self.assertEqual(poses[-1], (UNLOCK_ANGLE, UNLOCK_LIFT))
        self.assertTrue(all(angle == 0 for angle, _ in poses))
        self.assertTrue(all(b[1] >= a[1] for a, b in zip(poses, poses[1:])))
        self.assertEqual(unlock_pose(-1), poses[0])
        self.assertEqual(unlock_pose(2), poses[-1])
        self.assertAlmostEqual(poses[1][0] - poses[0][0], 0, places=5)
        self.assertAlmostEqual(poses[-1][0] - poses[-2][0], 0, places=5)
        self.assertAlmostEqual(poses[1][1] - poses[0][1], 0, places=7)
        self.assertAlmostEqual(poses[-1][1] - poses[-2][1], 0, places=7)

    def test_entire_shackle_lifts_straight_up(self):
        try:
            from PIL import Image, ImageDraw
            from vault.ui.scene import _lift_shackle
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        image = Image.new("RGBA", (100, 100))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 50, 8, 55), fill="white")
        draw.rectangle((75, 50, 83, 55), fill="white")
        raised = _lift_shackle(image, 79, 12, 20)
        left = raised.crop((0, 0, 9, raised.height)).getbbox()
        right = raised.crop((75, 0, 84, raised.height)).getbbox()
        self.assertEqual(left[1], 50 + 20 - 12)
        self.assertEqual(right[1], left[1])

    def test_no_artificial_hole_on_detached_end(self):
        try:
            from PIL import Image
            from vault.ui.scene import _split_shackle
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        original = Image.new("RGBA", (109, 109), (200, 200, 200, 255))
        arch, _ = _split_shackle(original)
        cut = round(original.height * 420 / 1090)
        self.assertEqual(arch.getpixel((35, cut + 1))[3], 0)
        self.assertEqual(arch.getpixel((35, cut - 1)), original.getpixel((35, cut - 1)))

    def test_right_leg_stays_in_lock_after_smaller_lift(self):
        try:
            from PIL import Image, ImageDraw
            from vault.ui.scene import _split_shackle, UNLOCK_LIFT, RIGHT_LEG_EXTENSION
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        image = Image.new("RGBA", (1090, 1090))
        draw = ImageDraw.Draw(image)
        draw.rectangle((316, 200, 434, 419), fill="white")
        draw.rectangle((659, 200, 777, 419), fill="white")
        arch, _ = _split_shackle(image)
        lift_px = round(image.height * UNLOCK_LIFT)
        self.assertLess(UNLOCK_LIFT, 0.075)
        self.assertGreater(RIGHT_LEG_EXTENSION, UNLOCK_LIFT)
        self.assertEqual(arch.getpixel((375, 420 + lift_px))[3], 0)
        self.assertEqual(arch.getpixel((718, 420 + lift_px))[3], 255)

    def test_fixed_icon_tint_matches_graphite_and_ignores_palette(self):
        try:
            from vault.ui import gfx, theme
            from vault.ui.scene import FLOATERS, SCENE_ICON_TINT
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        tiles = [sprite for _, sprite, *rest in FLOATERS if rest[-1] == "tile"]
        with patch.object(theme, "PRIMARY", ("#5B6069", "#B9BEC8")), \
             patch.object(theme, "dark", return_value=False):
            gfx.reset_palette_cache()
            graphite = {name: gfx.sprite(name, width=72).tobytes() for name in tiles}
        for primary in (("#EE3333", "#2255AA"), ("#008855", "#FF99CC")):
            with patch.object(theme, "PRIMARY", primary), patch.object(theme, "dark", return_value=False):
                gfx.reset_palette_cache()
                for name in tiles:
                    self.assertEqual(gfx.sprite(name, width=72, tint=SCENE_ICON_TINT).tobytes(), graphite[name])
        gfx.reset_palette_cache()

    def test_scene_applies_fixed_tint_only_to_floating_tiles(self):
        import tkinter as tk
        try:
            from vault.ui import gfx
            from vault.ui.scene import HeroScene, FLOATERS, SCENE_ICON_TINT
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Display unavailable: {exc}")
        try:
            root.geometry("700x700")
            with patch("vault.ui.scene.anim.enabled", return_value=False), \
                 patch.object(gfx, "sprite", wraps=gfx.sprite) as sprite:
                scene = HeroScene(root, bg="#FFFFFF", title="Test", subtitle="Test", animate=lambda: False)
                scene.pack(fill="both", expand=True)
                root.update()
                scene.force_layout()
                calls = sprite.call_args_list
                for _, name, *rest in FLOATERS:
                    expected = SCENE_ICON_TINT if rest[-1] == "tile" else None
                    matching = [call for call in calls if call.args and call.args[0] == name]
                    self.assertTrue(matching, name)
                    self.assertTrue(all(call.kwargs.get("tint") == expected for call in matching), name)
                scene.destroy()
        finally:
            root.destroy()

    def test_add_account_label_is_darker_only_in_dark_mode(self):
        import tkinter as tk
        try:
            from vault.ui import gfx, theme
            from vault.ui.scene import HeroScene
            from vault.ui.widgets import _darken
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Display unavailable: {exc}")
        try:
            root.geometry("700x700")
            with patch.object(theme, "PRIMARY", ("#5B6069", "#B9BEC8")):
                for dark_mode in (False, True):
                    with patch.object(theme, "dark", return_value=dark_mode), \
                         patch("vault.ui.scene.anim.enabled", return_value=False):
                        scene = HeroScene(root, bg="#FFFFFF", title="Test", subtitle="Test",
                                          button=("Add account", lambda: None), animate=lambda: False)
                        scene.pack(fill="both", expand=True)
                        root.update()
                        scene.force_layout()
                        expected_label = _darken("#B9BEC8", 0.28) if dark_mode else "#5B6069"
                        expected_icon = "#B9BEC8" if dark_mode else "#5B6069"
                        with patch.object(gfx, "text_image", wraps=gfx.text_image) as label, \
                             patch.object(gfx, "icon", wraps=gfx.icon) as icon:
                            scene._button._render("normal")
                        self.assertEqual(label.call_args.args[2], expected_label)
                        self.assertEqual(icon.call_args.args[2], expected_icon)
                        scene.destroy()
        finally:
            root.destroy()

    def test_live_unlock_and_reset(self):
        import time
        import tkinter as tk
        try:
            from vault.ui.scene import HeroScene, UNLOCK_SECONDS, UNLOCK_PAUSE_MS, UNLOCK_ANGLE, UNLOCK_LIFT
            from vault.ui import gfx
        except ImportError as exc:
            self.skipTest(f"UI dependencies unavailable: {exc}")
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Display unavailable: {exc}")
        try:
            root.geometry("700x700")
            with patch("vault.ui.scene.anim.enabled", return_value=True):
                scene = HeroScene(root, bg="#FFFFFF", title="Test", subtitle="Test", animate=lambda: True)
                scene.pack(fill="both", expand=True)
                root.update()
                scene.force_layout()
                self.assertEqual(UNLOCK_ANGLE, 0.0)
                calls = []
                scene.play_unlock(lambda: calls.append("unlocked"))
                end = time.monotonic() + UNLOCK_SECONDS + UNLOCK_PAUSE_MS / 1000 + 0.5
                while time.monotonic() < end and not calls:
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(calls, ["unlocked"])
                self.assertEqual(scene._open_frame_angle, UNLOCK_ANGLE)
                self.assertEqual(scene._open_frame_lift, round(scene._arch_height * UNLOCK_LIFT, 3))
                shackle = next(it for it in scene._items if it["name"] == "shackle")
                closed_center = shackle["x"] * gfx.scale()
                self.assertAlmostEqual(scene.coords(shackle["item"])[0],
                                       closed_center + scene._arch_center_offset[0])
                scene.reset_lock()
                self.assertIsNone(scene._open)
                self.assertFalse(scene._opened)
                scene.destroy()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
