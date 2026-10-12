import json
import tempfile
import time
import unittest
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from liquid_overlay import LiquidOverlay
from speech_motion import MotionSample

APP = QApplication.instance() or QApplication([])


class OverlayTests(unittest.TestCase):
    def test_exit_holds_colour_then_resets_while_hidden(self):
        for tint in (0., .65, 1.):
            self.blob.set_app_state('processing', 'polish')
            self.blob.transition = None
            self.blob.scale = 1.
            self.blob.green = tint
            self.blob.set_app_state('idle')
            self.blob.transition = ('out', time.monotonic()-.2, 1.)
            self.blob.last_tick = time.monotonic()-.04
            self.blob.tick()
            self.assertEqual(self.blob.green, tint)
            self.assertLess(self.blob.scale, 1.)
            self.blob.transition = ('out', time.monotonic()-1, 1.)
            self.blob.tick()
            self.assertFalse(self.blob.isVisible())
            self.assertEqual(self.blob.green, 0.)

    def test_automatic_cleanup_keeps_one_visible_blob_until_done(self):
        self.blob.set_app_state('recording')
        self.blob.transition = None
        self.blob.scale = 1.
        for _ in range(2):
            self.blob.set_app_state('processing', 'polish')
            self.assertTrue(self.blob.isVisible())
            self.assertIsNone(self.blob.transition)
            self.assertEqual(self.blob.scale, 1.)
        self.blob.last_tick = time.monotonic()-.04
        self.blob.tick()
        self.assertGreater(self.blob.green, 0.)
        self.assertLess(self.blob.green, 1.)
        self.blob.set_app_state('idle')
        self.assertEqual(self.blob.transition[0], 'out')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'overlay.json'
        self.level = MotionSample()
        self.blob = LiquidOverlay(lambda: self.level, self.path)

    def tearDown(self):
        self.blob.timer.stop()
        self.blob.close()
        self.temp.cleanup()

    def test_release_shrinks_and_stops_timer_without_reopening_for_transcription(self):
        self.blob.set_app_state('recording')
        self.blob.transition = ('in', time.monotonic()-1, 0)
        self.blob.tick()
        self.assertAlmostEqual(self.blob.scale, 1)
        self.blob.set_app_state('idle')
        self.blob.set_app_state('processing')
        self.assertEqual(self.blob.transition[0], 'out')
        self.blob.transition = ('out', time.monotonic()-1, 1)
        self.blob.tick()
        self.assertFalse(self.blob.isVisible())
        self.assertFalse(self.blob.timer.isActive())

    def test_live_level_and_silence_and_polish(self):
        self.blob.show_mode('recording')
        self.blob.transition = None
        self.level=MotionSample(True, .8, time.monotonic())
        for _ in range(10):
            self.blob.last_tick=time.monotonic()-.04
            self.blob.tick()
        self.assertGreater(self.blob.energy, .3)
        self.level=MotionSample()
        for _ in range(160):
            self.blob.last_tick=time.monotonic()-.04; self.blob.tick()
        self.assertAlmostEqual(self.blob.energy,.31,delta=.003)
        self.assertLess(self.blob.motion.activity,.001)
        self.blob.set_app_state('processing','polish')
        self.assertEqual(self.blob.mode,'polish')
        self.assertTrue(self.blob.windowFlags() & Qt.WindowType.WindowTransparentForInput)

    def test_settings_persist_and_invalid_positions_clamped(self):
        self.blob.change('size',60)
        self.assertEqual(json.loads(self.path.read_text())['size'],60)
        self.blob.settings.update(x=1,y=1,screen='disconnected monitor')
        self.blob.place()
        self.blob.remember_position()
        self.assertTrue(0 <= self.blob.settings['x'] <= 1)
        self.assertTrue(0 <= self.blob.settings['y'] <= 1)

    def test_disabling_shows_bar_and_polish_uses_green_mode(self):
        self.blob.change('enabled',False)
        self.blob.show_mode('recording')
        self.assertFalse(self.blob.isVisible())
        self.assertTrue(self.blob.bar.isVisible())
        self.assertEqual(self.blob.bar.mode, 'recording')
        self.blob.set_app_state('processing', 'polish')
        self.assertEqual(self.blob.bar.mode, 'polish')
        self.blob.set_app_state('idle')
        self.assertFalse(self.blob.bar.isVisible())
        self.assertFalse(self.blob.timer.isActive())

    def test_stale_audio_does_not_keep_blob_excited(self):
        self.blob.show_mode('recording')
        self.blob.transition = None
        self.level = MotionSample(True, 1., time.monotonic()-1.)
        self.blob.last_tick = time.monotonic()-.04
        self.blob.tick()
        self.assertEqual(self.blob.energy, .31)
        self.assertEqual(self.blob.motion.activity, 0)

    def test_maximum_size_stays_inside_window_during_entrance(self):
        self.blob.settings['size'] = 120
        self.blob.scale = 1.15
        self.blob.energy = 1
        self.blob.show()
        image = self.blob.grab().toImage()
        self.assertTrue(all(image.pixelColor(x, 0).alpha() == 0 for x in range(image.width())))
        self.assertTrue(all(image.pixelColor(0, y).alpha() == 0 for y in range(image.height())))

    def test_paint_and_placement_mode(self):
        self.blob.edit(True)
        self.blob.scale=1
        self.assertFalse(self.blob.grab().isNull())
        self.assertFalse(self.blob.windowFlags() & Qt.WindowType.WindowTransparentForInput)
        self.blob.edit(False)
        self.assertTrue(self.blob.windowFlags() & Qt.WindowType.WindowTransparentForInput)
