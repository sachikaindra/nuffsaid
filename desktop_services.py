"""GUI-thread clipboard and Windows output mute services."""
import ctypes
import logging
import threading
import time
from PyQt6.QtCore import QObject, QMimeData, QThread, pyqtSignal
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication


class DesktopServices(QObject):
    requested = pyqtSignal(object)
    notice_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.requested.connect(self._execute)
        self._muted = []
        self._com_initialized = False
        self.clipboard_lock = threading.Lock()

    def _execute(self, request):
        fn, event, result = request
        try:
            result.append((True, fn()))
        except Exception as exc:
            result.append((False, exc))
        finally:
            event.set()

    def call(self, fn):
        if QThread.currentThread() == self.thread():
            return fn()
        event, result = threading.Event(), []
        self.requested.emit((fn, event, result))
        # Operations finish before worker returns; never leave queued clipboard writes.
        event.wait()
        ok, value = result[0]
        if not ok:
            raise value
        return value

    @staticmethod
    def sequence():
        return ctypes.windll.user32.GetClipboardSequenceNumber()

    def snapshot(self):
        def capture():
            source = QApplication.clipboard().mimeData()
            target = QMimeData()
            before = self.sequence()
            if source:
                for fmt in source.formats():
                    payload = source.data(fmt)
                    if not payload.isEmpty():
                        target.setData(fmt, payload)
                if source.hasImage():
                    image = QImage(source.imageData())
                    if image.isNull():
                        # Windows can advertise an empty image after its owner exits.
                        # Keep any serialized formats; there is no decoded image to copy.
                        logging.warning('Clipboard advertises an image but provides no decoded pixels')
                    else:
                        target.setImageData(image.copy())
            if before != self.sequence():
                raise RuntimeError('Clipboard changed while being saved; please retry')
            return target
        return self.call(capture)

    def set_text(self, text):
        def put():
            QApplication.clipboard().setText(text)
            return self.sequence()
        return self.call(put)

    def text(self):
        return self.call(lambda: QApplication.clipboard().text())

    def restore(self, snapshot, expected_sequence):
        def put_back():
            # A newer user copy always takes priority.
            if self.sequence() == expected_sequence:
                QApplication.clipboard().setMimeData(snapshot)
        self.call(put_back)

    def mute_outputs(self):
        def mute():
            if self._muted:
                return
            from comtypes import CoInitialize, CLSCTX_ALL
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            if not self._com_initialized:
                CoInitialize()
                self._com_initialized = True
            devices = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(0, 1)
            try:
                for index in range(devices.GetCount()):
                    endpoint = devices.Item(index)
                    # QueryInterface acquires an independent COM reference.
                    # A ctypes cast aliases the original pointer without AddRef,
                    # so releasing both wrappers can crash inside _ctypes.
                    interface = endpoint.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    volume = interface.QueryInterface(IAudioEndpointVolume)
                    old = bool(volume.GetMute())
                    self._muted.append((volume, old))
                    volume.SetMute(1, None)
            except Exception:
                self._restore_outputs()
                raise
        self.call(mute)

    def _restore_outputs(self):
        pending = []
        for volume, previous in self._muted:
            try:
                volume.SetMute(int(previous), None)
            except Exception:
                pending.append((volume, previous))
                logging.exception('Could not restore an audio endpoint')
        self._muted = pending

    def restore_outputs(self):
        self.call(self._restore_outputs)


class ClipboardActions:
    def __init__(self, desktop, controller, config):
        self.desktop, self.controller, self.config = desktop, controller, config

    def capture_selection(self):
        from pynput import keyboard
        with self.desktop.clipboard_lock:
            saved = self.desktop.snapshot()
            seq = self.desktop.set_text('')
            try:
                with self.controller.pressed(keyboard.Key.ctrl):
                    self.controller.tap('c')
                deadline = time.monotonic() + 0.8
                while time.monotonic() < deadline:
                    time.sleep(0.025)
                    changed = self.desktop.sequence()
                    if changed != seq:
                        seq = changed
                        return self.desktop.text() or None
                return None
            finally:
                self.desktop.restore(saved, seq)

    def paste_text(self, text):
        from pynput import keyboard
        if not text:
            return False
        started = time.perf_counter()
        with self.desktop.clipboard_lock:
            saved = self.desktop.snapshot()
            seq = self.desktop.set_text(text)
            try:
                time.sleep(self.config.get('pre_paste_delay_ms', 80) / 1000)
                if self.desktop.sequence() != seq:
                    raise RuntimeError('Clipboard changed before paste; recover the text from History')
                with self.controller.pressed(keyboard.Key.ctrl):
                    self.controller.tap('v')
                logging.info('TIMING paste dispatched: %.3fs', time.perf_counter()-started)
                # Clipboard paste is asynchronous in browsers and Office.
                time.sleep(self.config.get('restore_delay_ms', 1000) / 1000)
                return True
            finally:
                self.desktop.restore(saved, seq)
                logging.info('TIMING paste and clipboard restoration: %.3fs', time.perf_counter()-started)
