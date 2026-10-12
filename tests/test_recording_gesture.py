import unittest

from recording_gesture import RecordingGesture


class RecordingGestureTests(unittest.TestCase):
    def test_hold_release_has_grace(self):
        g = RecordingGesture()
        self.assertEqual(g.press(0), 'start')
        self.assertEqual(g.release(2), .15)
        self.assertFalse(g.expire(2.1))
        self.assertTrue(g.expire(2.16))
        self.assertFalse(g.active)

    def test_double_tap_locks_then_next_press_stops(self):
        g = RecordingGesture()
        g.press(0)
        self.assertEqual(g.release(.1), .35)
        self.assertEqual(g.press(.2), 'lock')
        self.assertIsNone(g.release(.3))
        self.assertFalse(g.expire(30))
        self.assertTrue(g.locked)
        self.assertEqual(g.press(31), 'stop')
        self.assertIsNone(g.release(31.1))
        self.assertFalse(g.active)

    def test_accidental_release_resumes_hold_without_lock(self):
        g = RecordingGesture()
        g.press(0)
        g.release(2)
        self.assertIsNone(g.press(2.05))
        self.assertFalse(g.locked)
        self.assertFalse(g.expire(2.2))
        g.release(3)
        self.assertTrue(g.expire(3.16))

    def test_single_tap_finishes_after_double_tap_window(self):
        g = RecordingGesture()
        g.press(0)
        g.release(.1)
        self.assertTrue(g.expire(.46))
        self.assertEqual(g.press(1), 'start')

    def test_held_key_repeat_does_not_lock(self):
        g = RecordingGesture()
        g.press(0)
        self.assertIsNone(g.press(.1))
        self.assertFalse(g.locked)

    def test_cancel_or_timeout_clears_pending_gesture(self):
        for locked in (False, True):
            g = RecordingGesture()
            g.press(0)
            g.release(.1)
            if locked:
                g.press(.2)
            g.reset()
            self.assertIsNone(g.release(.3))
            self.assertFalse(g.expire(1))
            self.assertEqual(g.press(2), 'start')
