import math
import unittest
from PyQt6.QtWidgets import QApplication
from gel_renderer import GelRenderer
from speech_motion import FluidMotion, MotionSample, entrance_scale

APP = QApplication.instance() or QApplication([])


class GelTests(unittest.TestCase):
    def test_native_shader_transparency_glow_and_polish(self):
        renderer = GelRenderer()
        try:
            idle = renderer.render(256,1.4,.087,0,1,0)
            glow = renderer.render(256,1.4,.087,0,1,.5)
            green = renderer.render(256,1.4,.087,1,1,.5)
            self.assertEqual(glow.pixelColor(0,128).alpha(),0)
            self.assertEqual(idle.pixelColor(220,128).alpha(),0)
            self.assertGreater(glow.pixelColor(220,128).alpha(),0)
            # Red gel (2026-10-11): red-orange halo while listening, neutral clear-glass halo during cleanup.
            self.assertGreater(glow.pixelColor(220,128).red(),glow.pixelColor(220,128).blue())
            self.assertGreaterEqual(green.pixelColor(220,128).blue(),green.pixelColor(220,128).red())
            self.assertTrue(50 < idle.pixelColor(128,128).alpha() < 200)
            gone = renderer.render(256,1.4,.087,0,0,.5)
            self.assertEqual(gone.pixelColor(128,128).alpha(),0)
        finally:
            renderer.close()

    def test_entrance_has_small_diminishing_bounces_and_settles(self):
        peaks = [max(entrance_scale(i/1000) for i in range(a,b))
                 for a,b in [(130,250),(350,480),(570,720)]]
        self.assertTrue(1 < peaks[2] < peaks[1] < peaks[0] < 1.06)
        self.assertEqual(entrance_scale(0),0)
        self.assertEqual(entrance_scale(.72),1)

    def test_approved_speeds_idle_without_glow_and_bounded_shape(self):
        speeds=[]
        for sample,polish in [(MotionSample(),False),(MotionSample(True,0),False),
                              (MotionSample(True,1),False),(MotionSample(),True)]:
            motion=FluidMotion()
            for _ in range(800):
                motion.advance(.02,sample,polish)
                self.assertLessEqual(motion.deformation,.20)
            before=motion.phase
            motion.advance(.02,sample,polish)
            speeds.append((motion.phase-before)/.02)
            if not sample.speaking and not polish:
                self.assertEqual(motion.activity,0)
        for actual,expected in zip(speeds,[1.57872,2.6680368,2.956,2.3687378]):
            self.assertAlmostEqual(actual,expected,places=4)
