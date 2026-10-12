import math
import time
import unittest
import numpy as np
from speech_motion import SpeechMotion, FluidMotion, MotionSample, surface_radius


def syllables(rate, gain, seconds=4, chunk=1024):
    t = np.arange(int(16000*seconds), dtype=np.float32)/16000
    # Soft syllabic envelope with connected vowels, not on/off square pulses.
    envelope = .15 + .85 * (.5 + .5*np.sin(2*np.pi*rate*t))**2
    voice = gain*envelope*(np.sin(2*np.pi*170*t) + .3*np.sin(2*np.pi*510*t))
    analyzer = SpeechMotion()
    for start in range(0, len(voice), chunk):
        analyzer.feed(voice[start:start+chunk])
    return analyzer


class SpeechMotionTests(unittest.TestCase):
    def test_quiet_fast_speech_moves_faster_than_loud_slow_speech(self):
        quiet = syllables(5, .025)
        loud = syllables(1.5, .3)
        self.assertTrue(quiet.sample.speaking)
        self.assertGreater(quiet.sample.pace, .65)
        self.assertLess(loud.sample.pace, .2)

    def test_gain_and_callback_boundaries_do_not_change_pace(self):
        quiet = syllables(4, .025, chunk=1024).sample.pace
        loud = syllables(4, .3, chunk=320).sample.pace
        irregular = syllables(4, .025, chunk=777).sample.pace
        self.assertAlmostEqual(quiet, loud, delta=.06)
        self.assertAlmostEqual(quiet, irregular, delta=.06)

    def test_silence_low_noise_and_reset(self):
        analyzer = SpeechMotion()
        analyzer.feed(np.random.default_rng(0).normal(0, .0014, 16000))
        self.assertFalse(analyzer.sample.speaking)
        analyzer = syllables(4, .01)
        analyzer.feed(np.zeros(16000))
        self.assertFalse(analyzer.sample.speaking)
        analyzer.reset()
        self.assertFalse(analyzer.sample.speaking)
        self.assertEqual(len(analyzer.onsets), 0)

    def test_motion_has_fast_attack_long_release_and_continuous_idle(self):
        motion = FluidMotion()
        for _ in range(15):
            motion.advance(.02, MotionSample(True, 1, time.monotonic()))
        self.assertGreater(motion.energy, .8)
        before = motion.energy
        for _ in range(15):
            motion.advance(.02, MotionSample())
        self.assertGreater(motion.energy, before*.8)
        for _ in range(250):
            motion.advance(.02, MotionSample())
        self.assertAlmostEqual(motion.energy, .31, delta=.01)
        phase = motion.phase
        motion.advance(.02, MotionSample())
        self.assertGreater(motion.phase, phase)

    def test_deformation_is_bounded_at_idle_and_fast_speech(self):
        for energy, bound in [(0,.025), (1,.20)]:
            radii = [surface_radius(a, phase, energy)
                     for phase in np.linspace(0, 40, 40)
                     for a in np.linspace(0, math.tau, 181)]
            self.assertLessEqual(max(radii), 1+bound)
            self.assertGreaterEqual(min(radii), 1-bound)
            self.assertGreater(max(radii)-min(radii), bound)


if __name__ == '__main__':
    unittest.main()
