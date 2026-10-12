#!/usr/bin/env python3
"""
NuffSaid - Wispr Flow Clone for Windows 11
"""

import sys
import os
import copy

from speech_runtime import AdaptiveSpeechEngine, configure_cuda_dlls
configure_cuda_dlls()

import math
import logging
import threading
import time
import yaml
import numpy as np
import pyaudio
import requests
from dataclasses import dataclass
from typing import Optional, List, Set
from enum import Enum
from pathlib import Path
from personal_store import PersonalStore
from desktop_services import DesktopServices, ClipboardActions
from recovery_ui import HistoryDialog, DictionaryDialog
from native_shortcuts import NativeShortcuts
from instance_guard import InstanceGuard
from speech_motion import SpeechMotion
from recording_gesture import RecordingGesture

APP_DIR = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
# Keep the established storage location so existing history survives the rename.
DATA_DIR = APP_DIR / 'data' if (APP_DIR / 'portable.flag').exists() else Path(os.environ.get('LOCALAPPDATA', str(APP_DIR))) / 'DictationApp'

ASSET_DIR = Path(getattr(sys, '_MEIPASS', APP_DIR)) / 'assets'

if '--local-install' in sys.argv:
    DATA_DIR = APP_DIR / 'dist' / 'NuffSaid' / 'data'

CONFIG_PATH = (APP_DIR / 'dist' / 'NuffSaid' / 'config.yaml'
               if '--local-install' in sys.argv else APP_DIR / 'config.yaml')

# Greyscale text rendering: no coloured ClearType fringes on the brand fonts (owner review, 2026-10-12).
os.environ.setdefault('QT_QPA_PLATFORM', 'windows:fontengine=freetype')
from liquid_overlay import LiquidOverlay

# PyQt6
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QWidget, QMessageBox, QInputDialog, QDialog, QVBoxLayout, QLabel, QPushButton
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QAction, QFont, QPen, QBrush, QCursor
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject, QRectF
import ui_shell

# pynput for hotkeys
from pynput import keyboard

try:
    import pydirectinput
    PYDIRECTINPUT_AVAILABLE = True
except ImportError:
    PYDIRECTINPUT_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False

DEFAULT_CONFIG = {
    "audio": {
        "sample_rate": 16000,
        "channels": 1,
        "chunk_size": 1024,
        "format": "int16",
        "max_recording_seconds": 60
    },
    "stt": {
        "model": "turbo",
        "device": "auto",
        "compute_type": "auto",
        "language": "en",
        "beam_size": 5,
        "vad_filter": True,
        "vad_parameters": {
            "min_silence_duration_ms": 500,
            "speech_pad_ms": 400
        }
    },
    "llm": {
        "backend": "ollama",
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama3:instruct",
            "timeout": 30,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "num_predict": 512,
                "repeat_penalty": 1.1
            }
        }
    },
    "hotkeys": {
        "dictation_trigger": ["ctrl", "cmd"],
        "polish_trigger": ["cmd", "alt", "e"],
        "recover_trigger": ["cmd", "alt", "s"]
    },
    "ui": {
        "tray_icon_size": 16,
        "colors": {
            "idle": [128, 128, 128],
            "recording": [0, 255, 65],
            "processing": [30, 144, 255],
            "error": [255, 140, 0]
        }
    },
    "paste": {
        "pre_paste_delay_ms": 50,
        "use_direct_input": False
    },
    "logging": {
        "level": "INFO",
        "file": "dictation_app.log"
    }
}

from cleanup_text import PROMPT as SYSTEM_PROMPT
PROMPT_PATH = DATA_DIR / 'cleanup-prompt.txt'   # the user's own cleanup prompt; ours is used when absent


def cleanup_prompt():
    try:
        text = PROMPT_PATH.read_text(encoding='utf-8').strip()
        return text or SYSTEM_PROMPT
    except OSError:
        return SYSTEM_PROMPT


def set_cleanup_prompt(text):
    """Save a custom prompt, or None / ours to go back to the default."""
    if not text or text.strip() == SYSTEM_PROMPT.strip():
        PROMPT_PATH.unlink(missing_ok=True)
    else:
        PROMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        PROMPT_PATH.write_text(text.strip() + '\n', encoding='utf-8')

def load_config() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = CONFIG_PATH
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
            if user_config:
                for key, value in user_config.items():
                    if key in config and isinstance(config[key], dict) and isinstance(value, dict):
                        config[key].update(value)
                    else:
                        config[key] = value
        except Exception as e:
            print(f"Config load error: {e}")
    return config

CONFIG = load_config()

def shortcut_label(name):
    return '+'.join({'cmd': 'Win', 'ctrl': 'Ctrl', 'alt': 'Alt'}.get(k, k.upper())
                    for k in CONFIG['hotkeys'][name])

@dataclass
class AudioBuffer:
    data: np.ndarray
    sample_rate: int
    duration: float

@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration: float
    processing_time: float

@dataclass
class PolishResult:
    original_text: str
    polished_text: str
    processing_time: float
    model_used: str

@dataclass
class AppStats:
    total_dictations: int = 0
    total_polishes: int = 0
    last_transcript: str = ""
    last_polished: str = ""

class AppState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    ERROR = "error"

class AudioRecorder:
    def __init__(self):
        self.cfg = CONFIG["audio"]
        self._audio = pyaudio.PyAudio()
        self._stream = None
        self._recording = False
        self._buffer = []
        self._lock = threading.Lock()
        self._start_time = 0
        self._current_volume = 0.0
        self._motion = SpeechMotion(self.cfg['sample_rate'])

        self._format_map = {
            "int16": pyaudio.paInt16,
            "int32": pyaudio.paInt32,
            "float32": pyaudio.paFloat32,
        }

    def get_current_volume(self) -> float:
        return self._current_volume

    def get_motion(self):
        return self._motion.sample

    def _decode_audio(self, data):
        dtype, divisor = {'int16': (np.int16, 32768.), 'int32': (np.int32, 2147483648.),
                          'float32': (np.float32, 1.)}.get(self.cfg['format'], (np.int16, 32768.))
        samples = np.frombuffer(data, dtype=dtype).astype(np.float32) / divisor
        if self.cfg['channels'] > 1:
            samples = samples.reshape(-1, self.cfg['channels']).mean(axis=1)
        return samples

    def start_recording(self) -> bool:
        if self._recording:
            return False
        try:
            self._buffer = []
            self._recording = True
            self._start_time = time.time()
            self._current_volume = 0.0
            self._motion.reset()

            pa_format = self._format_map.get(self.cfg["format"], pyaudio.paInt16)
            self._stream = self._audio.open(
                format=pa_format,
                channels=self.cfg["channels"],
                rate=self.cfg["sample_rate"],
                input=True,
                frames_per_buffer=self.cfg["chunk_size"],
                stream_callback=self._callback,
                start=False
            )
            self._stream.start_stream()
            logging.info("Recording started")
            return True
        except Exception as e:
            logging.error(f"Failed to start recording: {e}")
            self._recording = False
            return False

    def _callback(self, in_data, frame_count, time_info, status):
        if self._recording:
            with self._lock:
                self._buffer.append(in_data)
                try:
                    chunk = self._decode_audio(in_data)
                    self._motion.feed(chunk)
                    rms = np.sqrt(np.mean(chunk ** 2))
                    norm = min(1.0, float(rms) * 32768.0 / 2500.0)
                    self._current_volume = self._current_volume * 0.25 + norm * 0.75
                except Exception:
                    pass
        return (None, pyaudio.paContinue)

    def stop_recording(self) -> Optional[AudioBuffer]:
        if not self._recording:
            return None
        self._recording = False
        self._current_volume = 0.0
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None

        duration = time.time() - self._start_time
        with self._lock:
            if not self._buffer:
                return None
            audio_data = b''.join(self._buffer)
            self._buffer = []

        audio_array = self._decode_audio(audio_data)
        logging.info(f"Recording stopped. Duration: {duration:.2f}s")
        return AudioBuffer(data=audio_array, sample_rate=self.cfg["sample_rate"], duration=duration)

    def cleanup(self):
        if self._recording:
            self.stop_recording()
        if self._audio:
            self._audio.terminate()

class STTEngine(AdaptiveSpeechEngine):
    def __init__(self):
        super().__init__(CONFIG['stt'], APP_DIR)

    def transcribe(self, audio_buffer, initial_prompt=None):
        started = time.time()
        text, info = self.transcribe_text(audio_buffer, initial_prompt)
        return TranscriptionResult(text=text, language=info.language,
            duration=len(audio_buffer) / 16000.0,
            processing_time=time.time() - started)

class LLMPolisher:
    def __init__(self):
        self.backend = CONFIG['llm'].get('backend', 'ollama')
        self.cfg = CONFIG["llm"]["ollama"]
        self._session = requests.Session()
        self._url = f"{self.cfg['base_url']}/api/generate"

    def preload(self):
        """Load on a background thread without recording or generating user text."""
        if self.backend == 'openrouter':
            return
        started = time.perf_counter()
        try:
            response = requests.post(self._url, json={
                'model': self.cfg['model'], 'stream': False,
                'keep_alive': self.cfg.get('keep_alive', '15m'),
                'options': self.cfg['options'],
            }, timeout=self.cfg['timeout'])
            response.raise_for_status()
            logging.info('TIMING cleanup preload: %.3fs', time.perf_counter()-started)
        except Exception:
            logging.warning('Cleanup preload unavailable; will retry on use', exc_info=True)

    def is_available(self) -> bool:
        if self.backend == 'openrouter':
            return (APP_DIR / 'dist' / 'NuffSaid' / 'data' / 'openrouter.key.dpapi').exists()
        try:
            return self._session.get(f"{self.cfg['base_url']}/api/tags", timeout=2).status_code == 200
        except Exception:
            return False

    def polish(self, text: str) -> PolishResult:
        from cleanup_text import short_fragment, validate_cleanup
        if short_fragment(text):
            return PolishResult(text, text, 0, 'unchanged-short-fragment')
        if self.backend == 'openrouter':
            from openrouter_cleanup import cleanup, load_key, MODEL
            if not text or not text.strip():
                return PolishResult(text, text, 0, MODEL)
            key = load_key(APP_DIR / 'dist' / 'NuffSaid' / 'data' / 'openrouter.key.dpapi')
            polished, elapsed = cleanup(requests.Session(), key, text, cleanup_prompt())
            logging.info('TIMING OpenRouter cleanup: %.3fs', elapsed)
            return PolishResult(original_text=text, polished_text=polished,
                                processing_time=elapsed, model_used=MODEL)
        if not text or not text.strip():
            return PolishResult(original_text=text, polished_text=text, processing_time=0, model_used=self.cfg["model"])

        start_time = time.time()
        prompt = f"<dictated_text>\n{text}\n</dictated_text>"
        payload = {
            "model": self.cfg["model"],
            "prompt": prompt,
            "system": cleanup_prompt(),
            "keep_alive": self.cfg.get("keep_alive", "15m"),
            "stream": False,
            "options": self.cfg["options"]
        }
        try:
            resp = self._session.post(self._url, json=payload, timeout=self.cfg["timeout"])
            resp.raise_for_status()
            response = resp.json()
            logging.info('TIMING cleanup: total=%.3fs load=%.3fs prompt=%.3fs generation=%.3fs tokens=%s',
                         time.time()-start_time, response.get('load_duration', 0)/1e9,
                         response.get('prompt_eval_duration', 0)/1e9,
                         response.get('eval_duration', 0)/1e9, response.get('eval_count', 0))
            if response.get('done_reason') == 'length':
                raise RuntimeError('Cleanup exceeded the model output limit; original text is saved in History')
            polished = response.get("response", "").strip()
            from cleanup_text import strip_preamble
            polished = strip_preamble(polished, text)
            if not polished:
                raise RuntimeError('Cleanup returned no text; original text is saved in History')
            from openrouter_cleanup import without_em_dashes
            polished = without_em_dashes(polished)
            polished = validate_cleanup(text, polished)
            return PolishResult(original_text=text, polished_text=polished, processing_time=time.time() - start_time, model_used=self.cfg["model"])
        except Exception as e:
            raise RuntimeError(f"LLM error: {e}")

class HotkeyManager:
    KEY_MAP = {
        'ctrl': keyboard.Key.ctrl_l, 'alt': keyboard.Key.alt_l,
        'shift': keyboard.Key.shift_l, 'cmd': keyboard.Key.cmd, 'win': keyboard.Key.cmd,
        'esc': keyboard.Key.esc,
    }
    for c in 'abcdefghijklmnopqrstuvwxyz0123456789':
        KEY_MAP[c] = keyboard.KeyCode.from_char(c)

    def __init__(self):
        self._listener = None
        self._pressed = set()
        self._bindings = []
        self._lock = threading.Lock()

    def _parse(self, k):
        k = k.lower().strip()
        return self.KEY_MAP[k] if k in self.KEY_MAP else keyboard.KeyCode.from_char(k)

    def add_binding(self, keys, on_press=None, on_release=None):
        self._bindings.append({
            'keys': [self._parse(k) for k in keys],
            'on_press': on_press,
            'on_release': on_release,
            'active': False
        })

    def _matches(self, req, pressed):
        for r in req:
            matched = False
            for p in pressed:
                if r == p or (getattr(r, 'char', None) is not None and r.char == getattr(p, 'char', None)) or (getattr(r, 'vk', None) is not None and r.vk == getattr(p, 'vk', None)):
                    matched = True
                    break
            if not matched:
                return False
        return True

    def _on_p(self, key):
        callbacks = []
        with self._lock:
            self._pressed.add(self._canonical(key))
            for b in self._bindings:
                if self._matches(b['keys'], self._pressed) and not b['active']:
                    b['active'] = True
                    if b['on_press']:
                        callbacks.append(b['on_press'])
        for callback in callbacks:
            callback()

    def _on_r(self, key):
        callbacks = []
        with self._lock:
            self._pressed.discard(self._canonical(key))
            for b in self._bindings:
                if b['active'] and not self._matches(b['keys'], self._pressed):
                    b['active'] = False
                    if b['on_release']:
                        callbacks.append(b['on_release'])
        for callback in callbacks:
            callback()

    @staticmethod
    def _canonical(key):
        aliases = {keyboard.Key.ctrl_r: keyboard.Key.ctrl_l,
                   keyboard.Key.alt_r: keyboard.Key.alt_l,
                   keyboard.Key.shift_r: keyboard.Key.shift_l,
                   keyboard.Key.cmd_r: keyboard.Key.cmd}
        return aliases.get(key, key)

    def wait_released(self, timeout=5):
        deadline = time.monotonic() + timeout
        modifiers = {keyboard.Key.ctrl_l, keyboard.Key.alt_l, keyboard.Key.shift_l, keyboard.Key.cmd}
        while time.monotonic() < deadline:
            with self._lock:
                if not (self._pressed & modifiers):
                    return
            time.sleep(0.02)
        raise RuntimeError('Release the shortcut keys and retry; text is available in History')

    def start(self):
        self._listener = keyboard.Listener(on_press=self._on_p, on_release=self._on_r)
        self._listener.start()
        logging.info('Hotkeys active: %s (dictate), %s (cleanup), %s (recover), Win+Alt+Q (quit)',
                     shortcut_label('dictation_trigger'), shortcut_label('polish_trigger'), shortcut_label('recover_trigger'))

    def stop(self):
        if self._listener:
            self._listener.stop()

class TrayIconGenerator:
    def __init__(self, size=16):
        self.size = size

    def get_icon(self, state: AppState) -> QIcon:
        color = CONFIG["ui"]["colors"].get(state.value, CONFIG["ui"]["colors"]["idle"])
        pixmap = QPixmap(str(ASSET_DIR / 'nuffsaid.png')).scaled(self.size, self.size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(*color))
        painter.setPen(Qt.PenStyle.NoPen)
        if state != AppState.IDLE:
            painter.drawEllipse(self.size - 7, self.size - 7, 6, 6)
        painter.end()
        return QIcon(pixmap)

class DictationTrayApp(QObject):
    state_changed = pyqtSignal(AppState, str)

    def __init__(self, on_quit, on_test_audio, get_audio_level_fn=None, actions=None, menu_hooks=None):
        super().__init__()
        self._menu_hooks = menu_hooks
        self._cleanup_toggle = None
        self._status_label = None
        self._on_quit = on_quit
        self._on_test_audio = on_test_audio
        self._get_audio_level_fn = get_audio_level_fn
        self._actions = actions or []
        self._icon_gen = TrayIconGenerator()
        self._menu = None
        self._tray = None
        self._hud = None
        self._cleanup_action = None
        self.state_changed.connect(self._on_state_changed)

    def initialize(self, app):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return False

        self._hud = LiquidOverlay(self._get_audio_level_fn, DATA_DIR / 'overlay.json')
        self._tray = QSystemTrayIcon()
        self._tray.setToolTip("NuffSaid — Ctrl+Win to dictate")
        
        # Build persistent menu
        self._create_menu()
        
        # Open menu on ANY click (Left or Right click)
        self._tray.activated.connect(self._on_tray_click)
        self._tray.setIcon(self._icon_gen.get_icon(AppState.IDLE))
        self._tray.show()
        logging.info("System Tray initialized successfully")
        return True

    def _on_tray_click(self, reason):
        if self._menu:
            self._menu.popup(QCursor.pos())

    def _create_menu(self):
        if self._menu_hooks:
            h = self._menu_hooks
            self._menu, self._cleanup_toggle, self._status_label = ui_shell.build_tray_menu(
                h['open_home'], h['open_history'], h['open_dictionary'], self._on_test_audio,
                h['toggle_cleanup'], h['cleanup_on'], self._on_quit)
            self._tray.setContextMenu(self._menu)
            self.refresh_cleanup_status()
            return
        self._create_classic_menu()

    def _create_classic_menu(self):
        self._menu = QMenu()

        title = QAction("NuffSaid (Active)", self._menu)
        title.setEnabled(False)
        self._menu.addAction(title)
        self._menu.addSeparator()

        hotkey_info = QAction("Hold Ctrl+Win to Dictate", self._menu)
        hotkey_info.setEnabled(False)
        self._menu.addAction(hotkey_info)
        for label in ('Double-tap Ctrl+Win: hands-free; press again to finish',
                      'Escape: cancel recording'):
            info = QAction(label, self._menu)
            info.setEnabled(False)
            self._menu.addAction(info)
        for name, description in [('polish_trigger', 'Cleanup'), ('recover_trigger', 'Reinsert last dictation')]:
            info = QAction(f'{description}: {shortcut_label(name)}', self._menu)
            info.setEnabled(False)
            self._menu.addAction(info)
        self._menu.addSeparator()

        if self._on_test_audio:
            test_mic = QAction("Test Microphone (2s)", self._menu)
            test_mic.triggered.connect(self._on_test_audio)
            self._menu.addAction(test_mic)

        self._menu.addSeparator()

        for label, callback in self._actions:
            action = QAction(label, self._menu)
            action.triggered.connect(callback)
            if label == 'Automatic light cleanup':
                action.setCheckable(True)
                self._cleanup_action = action
            self._menu.addAction(action)

        # Big exit option
        quit_act = QAction("❌ Exit NuffSaid", self._menu)
        quit_act.triggered.connect(self._on_quit)
        self._menu.addAction(quit_act)

        self._tray.setContextMenu(self._menu)
        self.refresh_cleanup_status()

    def refresh_cleanup_status(self):
        enabled = bool(CONFIG.get('enhancement', {}).get('automatic', False))
        if self._cleanup_action:
            self._cleanup_action.setChecked(enabled)
        if self._cleanup_toggle:
            self._cleanup_toggle.set_on(enabled)
        if self._tray:
            status = 'On' if enabled else 'Off'
            backend = CONFIG['llm'].get('backend', 'ollama')
            model = 'OpenRouter (free NVIDIA)' if backend == 'openrouter' else 'Ollama: ' + CONFIG['llm']['ollama']['model']
            self._tray.setToolTip(f'NuffSaid — Ctrl+Win to dictate\nAutomatic cleanup: {status}\n{model}')

    def _on_state_changed(self, state, msg=""):
        if self._status_label:
            self._status_label.setText({'recording': 'Listening', 'processing': 'Working'}.get(state.value, 'Ready'))
        if self._tray:
            self._tray.setIcon(self._icon_gen.get_icon(state))
        if self._hud:
            self._hud.set_app_state(state, msg)

    def set_state(self, state, msg=""):
        self.state_changed.emit(state, msg)

    def cleanup(self):
        if self._hud:
            self._hud.close()
        if self._tray:
            self._tray.hide()

class DictationController:
    def __init__(self):
        self._shutdown = False
        self._busy = False
        self._recording = False
        self._worker = None
        self._qt_app = QApplication.instance() or QApplication(sys.argv)
        self._qt_app.setQuitOnLastWindowClosed(False)
        self._desktop = DesktopServices()
        self._desktop.notice_requested.connect(self._notice)
        self._store = PersonalStore(DATA_DIR / 'personal.sqlite3')
        self._recorder = AudioRecorder()
        self._stt = STTEngine()
        self._polisher = LLMPolisher()
        self._paste = ClipboardActions(self._desktop, keyboard.Controller(), CONFIG['paste'])
        self._extractor = self._paste
        self._hotkeys = HotkeyManager()
        self._native_shortcuts = None
        self._tray = None
        self._history_window = None
        self._dictionary_window = None
        self._status_window = None
        self._limit_timer = QTimer()
        self._limit_timer.setSingleShot(True)
        self._limit_timer.timeout.connect(self._stop_on_main)
        self._gesture = RecordingGesture()
        self._release_timer = QTimer()
        self._release_timer.setSingleShot(True)
        self._release_timer.timeout.connect(self._release_expired)

    def initialize(self):
        logging.info("Initializing...")
        self._stt.warmup()

        self._hotkeys.add_binding(
            CONFIG["hotkeys"]["dictation_trigger"],
            on_press=self._on_dictate_start,
            on_release=self._on_dictate_stop
        )
        self._native_shortcuts = NativeShortcuts(self._qt_app)
        self._hotkeys.add_binding(['esc'], on_press=lambda: self._desktop.call(self._cancel_recording))
        try:
            self._native_shortcuts.register(CONFIG['hotkeys']['polish_trigger'], self._on_polish)
            self._native_shortcuts.register(CONFIG['hotkeys']['recover_trigger'], self._on_recover)
            self._native_shortcuts.register(['cmd', 'alt', 'h'], self._show_history)
            self._native_shortcuts.register(['cmd', 'alt', 'q'], self.shutdown)
        except Exception:
            self._native_shortcuts.close()
            raise

        ui_shell.apply(self._qt_app, ASSET_DIR.parent if (ASSET_DIR / 'fonts').exists() else APP_DIR)
        self._window = None
        self._tray = DictationTrayApp(
            menu_hooks=dict(open_home=self._show_status, open_history=self._show_history,
                            open_dictionary=self._show_dictionary, toggle_cleanup=self._toggle_cleanup,
                            cleanup_on=self._cleanup_on),
            on_quit=self.shutdown,
            on_test_audio=self._test_audio,
            get_audio_level_fn=self._recorder.get_motion,
            actions=[('Open NuffSaid', self._show_status),
                     ('History (Win+Alt+H)', self._show_history),
                     ('Personal dictionary', self._show_dictionary),
                     ('Blob appearance and position', self._show_blob_settings),
                     ('Automatic light cleanup', self._toggle_cleanup),
                     ('Cleanup provider / local model…', self._choose_cleanup_provider),
                     ('Speech recognition model…', self._choose_model),
                     ('Open settings file', lambda: os.startfile(str(CONFIG_PATH)))]
        )
        success = self._tray.initialize(self._qt_app)
        if success:
            self._hotkeys.start()
            threading.Thread(target=self._polisher.preload, daemon=True,
                             name='cleanup-preload').start()
        return success

    def run(self):
        self._qt_app.exec()

    def shutdown(self):
        if self._shutdown:
            return
        logging.info("Shutting down NuffSaid...")
        self._shutdown = True
        self._release_timer.stop()
        self._gesture.reset()
        self._limit_timer.stop()
        self._hotkeys.stop()
        if self._native_shortcuts:
            self._native_shortcuts.close()
        self._desktop.restore_outputs()
        self._recorder.cleanup()
        # Keep Qt serving queued clipboard restores until the worker finishes.
        if self._worker and self._worker.is_alive():
            self._quit_timer = QTimer()
            self._quit_timer.timeout.connect(self._finish_shutdown)
            self._quit_timer.start(50)
            return
        self._finish_shutdown()

    def _finish_shutdown(self):
        if self._worker and self._worker.is_alive():
            return
        self._desktop.restore_outputs()
        if self._tray:
            self._tray.cleanup()
        if self._qt_app:
            self._qt_app.quit()

    def _on_dictate_start(self):
        self._desktop.call(self._gesture_press)

    def _gesture_press(self):
        if self._shutdown or self._busy:
            return
        self._release_timer.stop()
        action = self._gesture.press(time.monotonic())
        if action == 'start':
            self._start_on_main()
            if not self._recording:
                self._gesture.reset()
        elif action == 'stop':
            self._stop_on_main()
        elif action == 'lock':
            logging.info('Hands-free recording locked; Ctrl+Win finishes, Escape cancels')

    def _release_expired(self):
        if self._gesture.expire(time.monotonic()):
            self._stop_on_main()
        elif self._gesture.deadline is not None:
            self._release_timer.start(max(1, math.ceil(
                (self._gesture.deadline - time.monotonic()) * 1000)))

    def _cancel_recording(self):
        if not self._recording:
            return
        self._release_timer.stop()
        self._limit_timer.stop()
        self._gesture.reset()
        self._recording = False
        try:
            self._recorder.stop_recording()
        except Exception:
            logging.exception('Could not stop cancelled recording')
        finally:
            self._desktop.restore_outputs()
            self._tray.set_state(AppState.IDLE)
        logging.info('Recording cancelled without transcription or insertion')

    def _start_on_main(self):
        if self._shutdown or self._busy or self._recording:
            return
        try:
            self._target_window = __import__('ctypes').windll.user32.GetForegroundWindow()
            if CONFIG['audio'].get('mute_while_recording', True):
                self._desktop.mute_outputs()
            if not self._recorder.start_recording():
                raise RuntimeError('Microphone could not start')
            self._recording = True
            self._tray.set_state(AppState.RECORDING)
            self._limit_timer.start(int(CONFIG['audio'].get('max_recording_seconds', 600) * 1000))
        except Exception as exc:
            self._desktop.restore_outputs()
            self._notice(str(exc))

    def _on_dictate_stop(self):
        def release():
            delay = self._gesture.release(time.monotonic())
            if delay is not None:
                self._release_timer.start(math.ceil(delay * 1000))
        self._desktop.call(release)

    def _stop_on_main(self):
        if self._shutdown or not self._recording:
            return
        self._release_timer.stop()
        self._gesture.reset()
        self._recording = False
        self._released_at = time.perf_counter()
        self._limit_timer.stop()
        if CONFIG.get('enhancement', {}).get('automatic', False):
            self._tray.set_state(AppState.PROCESSING, 'polish')
        else:
            self._tray.set_state(AppState.IDLE)
        try:
            buf = self._recorder.stop_recording()
        except Exception as exc:
            self._notice(f'Could not finish recording: {exc}')
            self._tray.set_state(AppState.ERROR)
            return
        finally:
            self._desktop.restore_outputs()
        if buf and len(buf.data) >= 1600:
            self._launch(self._process_dictation, buf)
        else:
            self._tray.set_state(AppState.IDLE)

    def _on_polish(self):
        logging.info('Cleanup shortcut received: %s', shortcut_label('polish_trigger'))
        self._desktop.call(lambda: self._launch(self._process_polish))

    def _on_recover(self):
        self._desktop.call(lambda: self._launch(self._recover))

    def _launch(self, action, *args):
        if self._shutdown or self._busy or self._recording:
            if not self._shutdown:
                self._notice('Please finish the current recording or wait for processing to complete.')
            return
        self._busy = True
        if action != self._process_dictation:
            self._target_window = __import__('ctypes').windll.user32.GetForegroundWindow()
        continuous_cleanup = (action == self._process_dictation and
                              CONFIG.get('enhancement', {}).get('automatic', False))
        self._tray.set_state(AppState.PROCESSING,
                             'polish' if action == self._process_polish or continuous_cleanup else '')
        def work():
            try:
                action(*args)
            except Exception as exc:
                logging.exception('Dictation operation failed')
                self._desktop.notice_requested.emit(str(exc))
            finally:
                self._desktop.call(self._done)
        self._worker = threading.Thread(target=work, daemon=True)
        self._worker.start()

    def _done(self):
        self._busy = False
        self._tray.set_state(AppState.IDLE)
        if self._status_window is not None:
            self._engine_label.setText(self._stt.description)

    def _insert(self, text):
        self._hotkeys.wait_released()
        if not self._shutdown:
            if __import__('ctypes').windll.user32.GetForegroundWindow() != self._target_window:
                raise RuntimeError(f'The active window changed. Your text is saved in History; use {shortcut_label("recover_trigger")} to insert the last dictation.')
            # End the visible operation now; the worker still safely protects
            # and restores the clipboard, without holding the blob onscreen.
            self._desktop.call(lambda: self._tray.set_state(AppState.IDLE))
            ready = time.perf_counter()
            if getattr(self, '_released_at', None) is not None:
                logging.info('TIMING release to text ready: %.3fs', ready-self._released_at)
                self._released_at = None
            self._paste.paste_text(text)

    def _process_dictation(self, buf):
        result = self._stt.transcribe(buf.data, initial_prompt=self._store.vocabulary_prompt())
        logging.info('TIMING transcription: %.3fs', result.processing_time)
        raw = result.text.strip()
        if not raw:
            return
        output = self._store.apply(raw)
        entry = self._store.save(raw, output)
        if CONFIG.get('enhancement', {}).get('automatic', False):
            try:
                self._tray.set_state(AppState.PROCESSING, 'polish')
                output = self._store.apply(self._polisher.polish(output).polished_text)
                self._store.update(entry, output)
            except Exception as exc:
                logging.warning('Cleanup skipped: %s', exc)
                self._desktop.notice_requested.emit(f'Cleanup unavailable; inserting original dictation. {exc}')
        self._insert(output)

    def _process_polish(self):
        self._hotkeys.wait_released()
        if self._shutdown:
            return
        selected = self._extractor.capture_selection()
        logging.info('Cleanup source: %s', 'selected text' if selected else 'last saved dictation')
        source = selected or self._store.latest()
        if not source:
            raise RuntimeError('Select text first, or record a dictation')
        entry = self._store.save(source, source, 'cleanup')
        output = self._store.apply(self._polisher.polish(source).polished_text)
        self._store.update(entry, output)
        self._insert(output)
        logging.info('Cleanup inserted successfully')

    def _recover(self):
        text = self._store.latest()
        if not text:
            raise RuntimeError('No saved dictation yet')
        self._insert(text)

    def _notice(self, message):
        if self._tray and self._tray._tray:
            self._tray._tray.showMessage('NuffSaid', message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def _open_on_launch(self):
        return bool(CONFIG.get('ui', {}).get('open_on_launch', True))

    def _cleanup_on(self):
        return bool(CONFIG.get('enhancement', {}).get('automatic', False))

    def _cleanup_desc(self):
        if CONFIG['llm'].get('backend', 'ollama') == 'openrouter':
            return 'OpenRouter · free NVIDIA model'
        return 'On this PC · Ollama ' + CONFIG['llm']['ollama']['model']

    def _open_window(self, page):
        if self._window is None:
            self._window = ui_shell.MainWindow(dict(
                store=self._store, engine=lambda: self._stt.description, copy=self._desktop.set_text,
                motion=lambda: self._recorder.get_motion() if self._recording else None,
                cleanup_on=self._cleanup_on, toggle_cleanup=self._toggle_cleanup, cleanup_desc=self._cleanup_desc,
                choose_cleanup=self._choose_cleanup_provider, choose_model=self._choose_model,
                test_mic=self._test_audio, open_config=lambda: os.startfile(str(CONFIG_PATH)),
                quit=self.shutdown, hud=lambda: self._tray._hud if self._tray else None, notice=self._notice,
                open_on_launch=self._open_on_launch,
                get_prompt=cleanup_prompt, default_prompt=lambda: SYSTEM_PROMPT, set_prompt=set_cleanup_prompt,
                set_open_on_launch=lambda v: self._save_setting('ui', 'open_on_launch', bool(v))))
        self._window.open(page)

    def _show_status(self):
        self._open_window('home')

    def _show_blob_settings(self):
        self._open_window('blob')

    def _show_history(self):
        self._open_window('history')

    def _show_dictionary(self):
        self._open_window('dictionary')

    def _save_setting(self, section, key, value):
        path = CONFIG_PATH
        data = yaml.safe_load(path.read_text(encoding='utf-8')) if path.exists() else {}
        data = data or {}
        data.setdefault(section, {})[key] = value
        temp = path.with_suffix('.yaml.tmp')
        temp.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
        temp.replace(path)
        CONFIG.setdefault(section, {})[key] = value

    def _choose_cleanup_provider(self):
        if self._busy or self._recording:
            self._notice('Finish the current dictation before switching cleanup providers.')
            return
        options = ['OpenRouter — free NVIDIA', 'Local Ollama']
        current = 0 if self._polisher.backend == 'openrouter' else 1
        selection, ok = QInputDialog.getItem(None, 'Cleanup provider',
            'Choose the cleanup provider. Changes apply immediately.', options, current, False)
        if not ok:
            return
        # A hotkey may have started work while the dialog was open.
        if self._busy or self._recording:
            self._notice('Finish the current dictation before switching.')
            return
        backend = 'openrouter' if selection == options[0] else 'ollama'
        try:
            if backend == 'openrouter':
                from openrouter_cleanup import load_key
                load_key(APP_DIR / 'dist' / 'NuffSaid' / 'data' / 'openrouter.key.dpapi')
            else:
                cfg = CONFIG['llm']['ollama']
                response = requests.get(cfg['base_url'] + '/api/tags', timeout=2)
                response.raise_for_status()
                models = [m['name'] for m in response.json().get('models', [])]
                if not models:
                    raise RuntimeError('No local Ollama models installed')
                index = models.index(cfg['model']) if cfg['model'] in models else 0
                model, ok = QInputDialog.getItem(None, 'Local cleanup model',
                    'Choose an installed Ollama model. Its first request may take longer to load.',
                    models, index, False)
                if not ok or self._busy or self._recording:
                    return
                self._save_setting('llm', 'ollama', dict(cfg, model=model))
            old = self._polisher
            self._save_setting('llm', 'backend', backend)
            self._polisher = LLMPolisher()
            if old.backend == 'ollama' and backend == 'openrouter':
                try:
                    requests.post(old._url, json={'model': old.cfg['model'], 'keep_alive': 0}, timeout=2)
                except requests.RequestException:
                    logging.warning('Ollama unload unavailable; model will expire normally')
            self._notice('Cleanup provider changed. No restart needed.')
        except Exception:
            self._notice('Could not change cleanup provider. Check that Ollama is running or the OpenRouter key is configured.')
        finally:
            self._tray.refresh_cleanup_status()

    def _toggle_cleanup(self):
        value = not CONFIG.get('enhancement', {}).get('automatic', False)
        try:
            self._save_setting('enhancement', 'automatic', value)
            self._notice(f'Automatic light cleanup {"enabled" if value else "disabled"}. {shortcut_label("polish_trigger")} cleans up selected text or the last dictation.')
        except Exception as exc:
            self._notice(f'Could not save settings: {exc}')
        finally:
            self._tray.refresh_cleanup_status()
            if self._window:
                self._window.refresh_cleanup()

    def _choose_model(self):
        model, ok = QInputDialog.getItem(None, 'Speech recognition model',
            'Larger models may improve accuracy but require more memory.\nThe model downloads on next start; restart after changing.',
            ['base', 'small', 'medium', 'large-v3', 'turbo'], editable=False)
        if ok:
            try:
                self._save_setting('stt', 'model', model)
                self._notice('Model saved. Restart the app to load it.')
            except Exception as exc:
                self._notice(f'Could not save model setting: {exc}')

    def _test_audio(self):
        if self._busy or self._recording:
            return
        self._start_on_main()
        if self._recording:
            self._limit_timer.start(2000)
            self._notice('Recording two seconds. Recognized text will be saved and inserted.')

def main():
    if '--self-test' in sys.argv:
        return self_test()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.FileHandler(DATA_DIR / 'app.log', encoding='utf-8'), logging.StreamHandler()]
    )
    logging.info("=" * 50)
    logging.info("NuffSaid Starting")
    logging.info('Interface: approved 3D gel overlay; source=%s; settings=%s', __file__, CONFIG_PATH)
    logging.info('Configured cleanup shortcut: %s', shortcut_label('polish_trigger'))
    logging.info("=" * 50)

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('NuffSaid')
    app.setApplicationDisplayName('NuffSaid')
    app.setWindowIcon(QIcon(str(ASSET_DIR / 'nuffsaid.png')))
    try:
        guard = InstanceGuard()
    except OSError as exc:
        logging.exception('Could not acquire application instance handles')
        QMessageBox.critical(None, 'NuffSaid', f'Windows could not start the app: {exc}')
        return 1
    if not guard.is_primary:
        try:
            if '--background' not in sys.argv:
                guard.activate()
                logging.info('Activated existing app window')
            else:
                logging.info('Background startup: app is already running')
        finally:
            guard.close()
        return 0
    controller = None
    try:
        controller = DictationController()
        if not controller.initialize():
            raise RuntimeError('The Windows system tray is unavailable')
        activation_timer = QTimer()
        activation_timer.timeout.connect(lambda: controller._show_status() if guard.activation_requested() else None)
        activation_timer.start(150)
        # The dashboard opens on launch unless the user turned it off (Settings); it always lives in the tray.
        if controller._open_on_launch() and '--background' not in sys.argv:
            controller._show_status()
            logging.info('Opened the dashboard on launch')
        else:
            logging.info('Started quietly in the system tray')
        logging.info('READY: initialized tray, model, shortcuts and activation service')
        controller.run()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception('Startup failed')
        QMessageBox.critical(None, 'NuffSaid', f'Could not start: {exc}\n\nSee {DATA_DIR / "app.log"}')
        return 1
    finally:
        if controller:
            controller.shutdown()
        guard.close()
    return 0


def self_test():
    """Packaged runtime test without recording, muting, pasting or global hooks."""
    import json
    import tempfile
    import traceback
    report = {}
    try:
        app = QApplication.instance() or QApplication([])
        desktop = DesktopServices()
        with tempfile.TemporaryDirectory() as folder:
            store = PersonalStore(Path(folder) / 'test.db')
            store.save('hello', 'Hello.')
            window = HistoryDialog(store, desktop)
            report['history_ui'] = window.output.toPlainText() == 'Hello.'
            dictionary = DictionaryDialog(store)
            report['dictionary_ui'] = dictionary.list.count() == 0
        from pycaw.pycaw import AudioUtilities
        report['output_devices'] = AudioUtilities.GetDeviceEnumerator().EnumAudioEndpoints(0, 1).GetCount()
        cfg = CONFIG['stt']
        if '--force-cpu' in sys.argv:
            CONFIG['stt'] = dict(cfg, device='cpu', compute_type='int8')
        engine = STTEngine()
        engine.warmup()
        report['model'] = engine.model_name
        report['device'] = engine.device
        report['compute_type'] = engine.compute_type
        report['fallback_reason'] = engine.fallback_reason
        report['speech_model'] = True
        report['ok'] = True
    except Exception:
        report['ok'] = False
        report['error'] = traceback.format_exc()
    (APP_DIR / 'self-test.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1

if __name__ == "__main__":
    sys.exit(main())
