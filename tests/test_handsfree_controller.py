import unittest
from unittest.mock import Mock, patch

from recording_gesture import RecordingGesture
from run_flow import DictationController, AppState


class HandsFreeControllerTests(unittest.TestCase):
    def controller(self):
        c = DictationController.__new__(DictationController)
        c._shutdown = c._busy = c._recording = False
        c._gesture = RecordingGesture()
        c._release_timer = Mock()
        c._limit_timer = Mock()
        c._desktop = Mock()
        c._desktop.call.side_effect = lambda fn: fn()
        c._recorder = Mock()
        c._tray = Mock()
        c._launch = Mock()
        return c

    def test_double_tap_keeps_one_recording_until_stop(self):
        c = self.controller()
        c._start_on_main = Mock(side_effect=lambda: setattr(c, '_recording', True))
        c._recorder.stop_recording.return_value = Mock(data=[0] * 1600)
        with patch('run_flow.time.monotonic', side_effect=[0, .1, .2, .3, 2]):
            c._gesture_press()
            c._on_dictate_stop()
            c._gesture_press()
            c._on_dictate_stop()
            c._recorder.stop_recording.assert_not_called()
            self.assertTrue(c._gesture.locked)
            c._gesture_press()
        c._start_on_main.assert_called_once()
        c._recorder.stop_recording.assert_called_once()
        c._launch.assert_called_once()
        self.assertFalse(c._recording)

    def test_escape_discards_audio_restores_outputs_and_resets_timers(self):
        c = self.controller()
        c._recording = True
        c._gesture.press(0)
        c._cancel_recording()
        c._recorder.stop_recording.assert_called_once()
        c._desktop.restore_outputs.assert_called_once()
        c._release_timer.stop.assert_called_once()
        c._limit_timer.stop.assert_called_once()
        c._launch.assert_not_called()
        c._tray.set_state.assert_called_with(AppState.IDLE)
        self.assertFalse(c._gesture.active)

    def test_idle_escape_does_nothing(self):
        c = self.controller()
        c._cancel_recording()
        c._recorder.stop_recording.assert_not_called()

    def test_failed_start_resets_gesture(self):
        c = self.controller()
        c._start_on_main = Mock()
        c._gesture_press()
        self.assertFalse(c._gesture.active)

    def test_busy_press_does_not_arm_recording(self):
        c = self.controller()
        c._busy = True
        c._gesture_press()
        self.assertFalse(c._gesture.active)
