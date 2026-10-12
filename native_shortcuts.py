"""Reserve tap shortcuts with Windows and report conflicts at startup."""
import ctypes
from ctypes import wintypes
from PyQt6.QtCore import QAbstractNativeEventFilter, QTimer


class NativeShortcuts(QAbstractNativeEventFilter):
    def __init__(self, app, api=None):
        super().__init__()
        self.app = app
        self.api = api or ctypes.WinDLL('user32', use_last_error=True)
        self.callbacks = {}
        app.installNativeEventFilter(self)

    def register(self, keys, callback):
        modifiers = 0x4000  # MOD_NOREPEAT
        bits = {'alt': 1, 'ctrl': 2, 'shift': 4, 'cmd': 8, 'win': 8}
        ordinary = []
        for key in keys:
            if key in bits:
                modifiers |= bits[key]
            else:
                ordinary.append(key)
        if len(ordinary) != 1 or len(ordinary[0]) != 1:
            raise ValueError('Tap shortcuts require modifiers and one letter or digit')
        identity = 0x4100 + len(self.callbacks)
        if not self.api.RegisterHotKey(None, identity, modifiers, ord(ordinary[0].upper())):
            raise RuntimeError(f'Shortcut {"+".join(keys)} is already in use or unavailable. Change it in config.yaml.')
        self.callbacks[identity] = callback

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.callbacks:
                QTimer.singleShot(0, self.callbacks[msg.wParam])
                return True, 0
        return False, 0

    def close(self):
        for identity in self.callbacks:
            self.api.UnregisterHotKey(None, identity)
        self.callbacks.clear()
        self.app.removeNativeEventFilter(self)
