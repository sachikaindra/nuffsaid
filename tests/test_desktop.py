"""Windows integration checks: preserve real clipboard around test fixtures."""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QMimeData, QUrl
from PyQt6.QtGui import QImage, QColor
from desktop_services import DesktopServices, ClipboardActions

APP = QApplication.instance() or QApplication([])


class ClipboardTests(unittest.TestCase):
    def setUp(self):
        self.desktop = DesktopServices()
        self.original = self.desktop.snapshot()

    def tearDown(self):
        self.desktop.restore(self.original, self.desktop.sequence())
        APP.processEvents()

    def test_rich_clipboard_restored_after_paste(self):
        data = QMimeData()
        data.setText('Original text')
        data.setHtml('<b>Original text</b>')
        data.setUrls([QUrl.fromLocalFile('C:/example.txt')])
        image = QImage(8, 8, QImage.Format.Format_ARGB32)
        image.fill(QColor('red'))
        data.setImageData(image)
        QApplication.clipboard().setMimeData(data)
        actions = ClipboardActions(self.desktop, MagicMock(), {'pre_paste_delay_ms': 0, 'restore_delay_ms': 0})
        self.assertTrue(actions.paste_text('Narrated text'))
        restored = QApplication.clipboard().mimeData()
        self.assertEqual(restored.text(), 'Original text')
        self.assertIn('<b>Original text</b>', restored.html())
        self.assertEqual(restored.urls()[0].toLocalFile(), 'C:/example.txt')
        self.assertEqual(QImage(restored.imageData()).pixelColor(0, 0), QColor('red'))

    def test_new_user_copy_is_not_overwritten(self):
        self.desktop.set_text('original')
        saved = self.desktop.snapshot()
        seq = self.desktop.set_text('dictation')
        self.desktop.set_text('new user copy')
        self.desktop.restore(saved, seq)
        self.assertEqual(self.desktop.text(), 'new user copy')

    def test_selection_identical_to_existing_clipboard(self):
        self.desktop.set_text('same text')
        controller = MagicMock()
        controller.tap.side_effect = lambda key: self.desktop.set_text('same text')
        actions = ClipboardActions(self.desktop, controller, {})
        self.assertEqual(actions.capture_selection(), 'same text')
        self.assertEqual(self.desktop.text(), 'same text')

    def test_restore_after_keyboard_failure(self):
        self.desktop.set_text('keep me')
        controller = MagicMock()
        controller.tap.side_effect = RuntimeError('keyboard failure')
        actions = ClipboardActions(self.desktop, controller, {'pre_paste_delay_ms': 0})
        with self.assertRaises(RuntimeError):
            actions.paste_text('dictation')
        self.assertEqual(self.desktop.text(), 'keep me')


class MuteTests(unittest.TestCase):
    def test_all_output_endpoints_and_original_states_restored(self):
        # Mock COM endpoint objects, not the real user's speaker state.
        from pycaw.pycaw import AudioUtilities
        volumes = [Mock(), Mock()]
        volumes[0].GetMute.return_value = 0
        volumes[1].GetMute.return_value = 1
        devices = Mock()
        devices.GetCount.return_value = 2
        endpoints = [Mock(), Mock()]
        for endpoint, volume in zip(endpoints, volumes):
            endpoint.Activate.return_value.QueryInterface.return_value = volume
        devices.Item.side_effect = endpoints
        enumerator = Mock()
        enumerator.EnumAudioEndpoints.return_value = devices
        service = DesktopServices()
        with patch.object(AudioUtilities, 'GetDeviceEnumerator', return_value=enumerator):
            service.mute_outputs()
        enumerator.EnumAudioEndpoints.assert_called_once_with(0, 1)
        for volume in volumes:
            volume.SetMute.assert_called_with(1, None)
        service.restore_outputs()
        volumes[0].SetMute.assert_called_with(0, None)
        volumes[1].SetMute.assert_called_with(1, None)


class NativeShortcutTests(unittest.TestCase):
    def test_register_dispatch_and_unregister(self):
        import ctypes
        from ctypes import wintypes
        from native_shortcuts import NativeShortcuts
        api = Mock()
        api.RegisterHotKey.return_value = 1
        shortcuts = NativeShortcuts(APP, api)
        callback = Mock()
        try:
            shortcuts.register(['cmd', 'alt', 'e'], callback)
            api.RegisterHotKey.assert_called_once_with(None, 0x4100, 0x4009, ord('E'))
            msg = wintypes.MSG()
            msg.message = 0x0312
            msg.wParam = 0x4100
            self.assertEqual(shortcuts.nativeEventFilter(b'windows_generic_MSG', ctypes.addressof(msg)), (True, 0))
            APP.processEvents()
            callback.assert_called_once()
        finally:
            shortcuts.close()
        api.UnregisterHotKey.assert_called_once_with(None, 0x4100)

    def test_conflict_reported(self):
        from native_shortcuts import NativeShortcuts
        api = Mock()
        api.RegisterHotKey.return_value = 0
        shortcuts = NativeShortcuts(APP, api)
        try:
            with self.assertRaisesRegex(RuntimeError, 'already in use'):
                shortcuts.register(['cmd', 'alt', 'w'], Mock())
            self.assertFalse(shortcuts.callbacks)
        finally:
            shortcuts.close()


if __name__ == '__main__':
    unittest.main()
