"""Free-only text cleanup and Windows user-bound secret storage."""
import ctypes
from ctypes import wintypes
import time
import re
import requests
from cleanup_text import strip_preamble, validate_cleanup

MODEL = 'nvidia/nemotron-3.5-lightning:free'
BASE = 'https://openrouter.ai/api/v1'


def without_em_dashes(text):
    """Enforce the user's punctuation preference even if a provider ignores it."""
    text = re.sub(r'\s*\u2014\s*', '. ', text)
    text = re.sub(r'\s+\u2013\s+', '. ', text)
    text = re.sub(r'([.!?])\. ', r'\1 ', text)
    return re.sub(r'([.!?]\s+)([a-z])', lambda m: m[1] + m[2].upper(), text).strip()


class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]


def protect(data, decrypt=False):
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    api = ctypes.WinDLL('crypt32', use_last_error=True)
    fn = api.CryptUnprotectData if decrypt else api.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                   ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


def load_key(path):
    return protect(path.read_bytes(), decrypt=True).decode('utf-8')


def cleanup(session, key, text, instructions, timeout=60):
    # Network inactivity protection only; no short deadline discards slow results.
    payload = {
        'model': MODEL,
        'messages': [{'role': 'system', 'content': instructions},
                     {'role': 'user', 'content': '<dictated_text>\n' + text + '\n</dictated_text>'}],
        'provider': {'max_price': {'prompt': 0, 'completion': 0, 'request': 0},
                     'allow_fallbacks': False},
        'reasoning': {'enabled': False},
        'max_tokens': min(4096, max(256, len(text))),
        'stream': False,
    }
    started = time.perf_counter()
    try:
        response = session.post(BASE + '/chat/completions', json=payload,
                                headers={'Authorization': 'Bearer ' + key},
                                timeout=(2, timeout), allow_redirects=False)
    except requests.RequestException:
        raise RuntimeError('Online cleanup connection failed or timed out') from None
    if response.status_code != 200:
        raise RuntimeError('Online cleanup unavailable (HTTP %s)' % response.status_code)
    try:
        choice = response.json()['choices'][0]
        output = strip_preamble(choice['message']['content'], text)
        if choice.get('finish_reason') != 'stop' or not output:
            raise ValueError()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError('Online cleanup returned incomplete text') from None
    return validate_cleanup(text, without_em_dashes(output)), time.perf_counter() - started
