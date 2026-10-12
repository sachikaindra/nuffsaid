"""Windows instance ownership and activation; handles disappear on process exit."""
import ctypes
import getpass
import hashlib
from ctypes import wintypes


class InstanceGuard:
    def __init__(self, name=None):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateMutexW.restype = wintypes.HANDLE
        self.api.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        self.api.CreateEventW.restype = wintypes.HANDLE
        self.api.SetEvent.argtypes = [wintypes.HANDLE]
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        suffix = hashlib.sha256(getpass.getuser().encode()).hexdigest()[:16]
        self.name = name or f'Local\\DictationApp-{suffix}'
        self.mutex = self.api.CreateMutexW(None, False, self.name)
        error = ctypes.get_last_error()
        if not self.mutex:
            raise ctypes.WinError(error)
        self.is_primary = error != 183  # ERROR_ALREADY_EXISTS
        self.event = self.api.CreateEventW(None, False, False, self.name + '-activate')
        if not self.event:
            error = ctypes.get_last_error()
            self.close()
            raise ctypes.WinError(error)

    def activate(self):
        if not self.api.SetEvent(self.event):
            raise ctypes.WinError(ctypes.get_last_error())

    def activation_requested(self):
        return self.api.WaitForSingleObject(self.event, 0) == 0

    def close(self):
        for name in ('event', 'mutex'):
            handle = getattr(self, name, None)
            if handle:
                self.api.CloseHandle(handle)
                setattr(self, name, None)
