"""First-run setup: say exactly what gets downloaded, how big it is and why, then download it with live progress.
Speech model (everyone) from Hugging Face; the optional NVIDIA boost (NVIDIA cards only) from NVIDIA's official
packages on PyPI. Every file is size- or checksum-verified. After this, NuffSaid works offline."""
import hashlib
import json
import logging
import os
import subprocess
import time
import zipfile
from pathlib import Path

import requests
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QApplication, QFrame

import ui_shell as ui
from speech_runtime import HOME

MODEL_REPO = 'mobiuslabsgmbh/faster-whisper-large-v3-turbo'   # what faster-whisper uses for "turbo"
MODEL_FILES = ['config.json', 'preprocessor_config.json', 'tokenizer.json', 'vocabulary.json', 'model.bin']
GPU_WHEELS = [('nvidia-cublas-cu12', '12.9.2.10'), ('nvidia-cudnn-cu12', '9.26.0.51'),
              ('nvidia-cuda-runtime-cu12', '12.9.79'), ('nvidia-cuda-nvrtc-cu12', '12.9.86')]
INSTAGRAM = 'https://instagram.com/nuffsaid.app'


def model_dir(name='turbo'):
    return HOME / 'models' / name


def model_ready(app_dir, name='turbo'):
    """True when a complete model is already on this PC (downloaded, or bundled next to the app)."""
    for folder in (Path(app_dir) / name, Path(app_dir) / 'models' / name, model_dir(name)):
        if (folder / 'model.bin').is_file() and (folder / 'config.json').is_file():
            return True
    return False


def gpu_ready():
    return (HOME / 'cuda' / 'cublas64_12.dll').is_file() and any((HOME / 'cuda').glob('cudnn*64_9.dll'))


def graphics_cards():
    """Names of the PC's graphics adapters (Windows), e.g. ['NVIDIA GeForce RTX 3080']."""
    try:
        out = subprocess.run(['powershell', '-NoProfile', '-Command', '(Get-CimInstance Win32_VideoController).Name'],
                             capture_output=True, text=True, timeout=15, creationflags=0x08000000).stdout
        return [line.strip() for line in out.splitlines() if line.strip()]
    except Exception:
        return []


def microphone():
    try:
        import pyaudio
        pa = pyaudio.PyAudio()
        try:
            name = pa.get_default_input_device_info().get('name', '')
            try:   # PortAudio hands back UTF-8 bytes decoded as Latin-1 on some drivers (RÃ˜DE -> RØDE)
                name = name.encode('cp1252').decode('utf-8')
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            return name
        finally:
            pa.terminate()
    except Exception:
        return ''


def plan(with_gpu):
    """List of packages: dict(name, why, source, size, files=[(url, dest, size, sha256|None)])."""
    files, total = [], 0
    tree = {f['path']: f for f in requests.get(f'https://huggingface.co/api/models/{MODEL_REPO}/tree/main', timeout=20).json()}
    for name in MODEL_FILES:
        size = tree[name]['size']
        sha = (tree[name].get('lfs') or {}).get('oid')
        files.append((f'https://huggingface.co/{MODEL_REPO}/resolve/main/{name}', model_dir() / name, size, sha))
        total += size
    pkgs = [dict(key='model', name='Speech model', why='Whisper turbo. Turns your voice into text, on this PC.',
                 source='Hugging Face', size=total, files=files)]
    if with_gpu:
        gfiles, gtotal = [], 0
        for package, version in GPU_WHEELS:
            info = requests.get(f'https://pypi.org/pypi/{package}/{version}/json', timeout=20).json()
            wheel = next(f for f in info['urls'] if f['filename'].endswith('win_amd64.whl'))
            gfiles.append((wheel['url'], HOME / 'downloads' / wheel['filename'], wheel['size'], wheel['digests']['sha256']))
            gtotal += wheel['size']
        pkgs.append(dict(key='gpu', name='NVIDIA boost', why='cuBLAS + cuDNN. Lets your NVIDIA card do the work, several times faster.',
                         source="NVIDIA's official packages (PyPI)", size=gtotal, files=gfiles))
    return pkgs


class Downloader(QThread):
    progress = pyqtSignal(str, int, int, float)   # package key, bytes done, bytes total, speed (bytes/s)
    finished_pkg = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, packages):
        super().__init__()
        self.packages, self.stop = packages, False

    def run(self):
        try:
            for pkg in self.packages:
                done, started = 0, time.monotonic()
                for url, dest, size, sha in pkg['files']:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if dest.is_file() and dest.stat().st_size == size:
                        done += size; self.progress.emit(pkg['key'], done, pkg['size'], 0.); continue
                    part = dest.with_name(dest.name + '.part')
                    have = part.stat().st_size if part.is_file() else 0
                    headers = {'Range': f'bytes={have}-'} if have else {}
                    with requests.get(url, stream=True, timeout=30, headers=headers) as r:
                        if r.status_code == 200:
                            have = 0
                        elif r.status_code != 206:
                            r.raise_for_status()
                        with open(part, 'ab' if have else 'wb') as fh:
                            for chunk in r.iter_content(1 << 20):
                                if self.stop:
                                    return
                                fh.write(chunk); have += len(chunk)
                                elapsed = max(.5, time.monotonic() - started)
                                self.progress.emit(pkg['key'], done + have, pkg['size'], (done + have) / elapsed)
                    if part.stat().st_size != size:
                        raise RuntimeError(f'{dest.name} downloaded incompletely. Try again.')
                    if sha:
                        h = hashlib.sha256()
                        with open(part, 'rb') as fh:
                            for chunk in iter(lambda: fh.read(1 << 22), b''):
                                h.update(chunk)
                        if h.hexdigest() != sha:
                            part.unlink(missing_ok=True)
                            raise RuntimeError(f'{dest.name} failed its checksum. Try again.')
                    part.replace(dest)
                    done += size
                if pkg['key'] == 'gpu':
                    cuda = HOME / 'cuda'; cuda.mkdir(parents=True, exist_ok=True)
                    for _, wheel, _, _ in pkg['files']:
                        with zipfile.ZipFile(wheel) as z:
                            for member in z.namelist():
                                if member.lower().endswith('.dll'):
                                    (cuda / Path(member).name).write_bytes(z.read(member))
                        wheel.unlink(missing_ok=True)
                self.finished_pkg.emit(pkg['key'])
        except Exception as exc:
            logging.exception('First-run download failed')
            self.failed.emit(str(exc) or type(exc).__name__)


def human(n):
    return f'{n / 1e9:.2f} GB' if n >= 1e9 else f'{n / 1e6:.0f} MB'


class Bar(QWidget):
    def __init__(self):
        super().__init__(); self.setFixedHeight(6); self.p = 0.

    def set(self, p):
        self.p = max(0., min(1., p)); self.update()

    def paintEvent(self, e):
        from PyQt6.QtGui import QPainter, QColor
        q = QPainter(self); q.setRenderHint(QPainter.RenderHint.Antialiasing); q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor('#1a1a1a')); q.drawRoundedRect(0, 0, self.width(), 6, 3, 3)
        q.setBrush(QColor(ui.W)); q.drawRoundedRect(0, 0, int(self.width() * self.p), 6, 3, 3); q.end()


class SetupWindow(ui.Sheet):
    """The first thing a new user sees. Ends on YOU'RE IN. with the follow button."""
    done = pyqtSignal(bool)

    def __init__(self):
        super().__init__(962, 622)
        self.setWindowTitle('NuffSaid · setup')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        close = ui.Link('✕', ui.G, self); close.setFont(ui.body(13)); close.setGeometry(918, 8, 28, 26); close.clicked.connect(self.quit)
        ui.label('NuffSaid · setup', ui.mono(11), ui.G, self).move(18, 13)
        self.page = QWidget(self); self.page.setGeometry(0, 40, 962, 582)
        self.rows, self.worker, self.packages = {}, None, []
        self.show_intro()

    # ---- screen 1: what's on this PC, what will download --------------------------------------------------
    def show_intro(self):
        p = self.page
        ui.Headline('GIVE US', 112, stretch=1.15, stop=False, parent=p).move(44, 34)
        ui.Headline('A MINUTE', 112, stretch=1.15, parent=p, live=lambda: None).move(44, 160)   # the gel drifts like the app's
        self.side = ui.label('Downloading the parts that fit your PC.\nOnce. Then it never needs the internet.', ui.mono(11), ui.G, p)
        self.side.setGeometry(48, 330, 420, 60)
        self.note = ui.label('', ui.body(12), ui.G2, p, wrap=True); self.note.setGeometry(48, 470, 420, 60)
        self.list = QWidget(p); self.list.setGeometry(520, 30, 400, 440)
        self.lay = QVBoxLayout(self.list); self.lay.setContentsMargins(0, 0, 0, 0); self.lay.setSpacing(0)
        self.status = ui.label('Checking your PC…', ui.body(13), ui.G, self.list); self.lay.addWidget(self.status); self.lay.addStretch(1)
        self.go = ui.Pill('Start', p); self.go.move(520, 500); self.go.clicked.connect(self.start); self.go.setEnabled(False)
        self.go.setStyleSheet(f"QPushButton {{ color:{ui.K}; background:{ui.W}; border:1px solid {ui.W}; border-radius:13px; padding:0 18px; }} QPushButton:disabled {{ background:#333; border-color:#333; }}")
        self.skip_gpu = ui.Pill('Skip NVIDIA boost', p); self.skip_gpu.move(600, 500); self.skip_gpu.hide(); self.skip_gpu.clicked.connect(self.no_gpu)
        QApplication.processEvents()
        self.mic = microphone()
        self.cards = graphics_cards()
        self.nvidia = next((c for c in self.cards if 'nvidia' in c.lower()), '')
        self.want_gpu = bool(self.nvidia) and not gpu_ready()
        self.build_list()

    def build_list(self):
        while self.lay.count():
            w = self.lay.takeAt(0).widget()
            if w:
                w.hide(); w.setParent(None); w.deleteLater()
        try:
            self.packages = plan(self.want_gpu)
        except Exception as exc:
            self.lay.addWidget(ui.label(f"Can't reach the download servers right now.\n{exc}", ui.body(13), ui.G, wrap=True))
            retry = ui.Pill('Try again'); retry.clicked.connect(self.build_list); self.lay.addWidget(retry); self.lay.addStretch(1)
            return
        self.add_info('01', 'Microphone', self.mic or 'None found. Plug one in; NuffSaid uses your default microphone.')
        for i, pkg in enumerate(self.packages, 2):
            self.add_pkg(f'0{i}', pkg)
        if not self.nvidia:
            card = self.cards[0] if self.cards else 'Your graphics card'
            self.add_info(f'0{len(self.packages) + 2}', 'Graphics',
                          f"{card} isn't used by the speech engine (it only speeds up on NVIDIA). NuffSaid runs on your processor. Nothing extra to download.")
        elif not self.want_gpu:
            self.add_info(f'0{len(self.packages) + 2}', 'NVIDIA boost',
                          'Already on this PC.' if gpu_ready() else 'Skipped. NuffSaid runs on your processor. Add it later by running setup again.')
        self.lay.addStretch(1)
        total = sum(p['size'] for p in self.packages)
        self.note.setText(f'Total {human(total)}. Files come from Hugging Face and NVIDIA\'s official servers and are checked before use. '
                          'Nothing else is installed, nothing runs in the background.')
        self.go.setEnabled(True); self.skip_gpu.setVisible(self.want_gpu)

    def add_info(self, num, title, text):
        row = QFrame(); row.setStyleSheet(f'QFrame {{ border-bottom:1px solid {ui.LINE}; }} QLabel {{ border:none; }}')
        v = QVBoxLayout(row); v.setContentsMargins(0, 14, 0, 14); v.setSpacing(6)
        h = QHBoxLayout(); h.addWidget(ui.label(num, ui.mono(11), ui.G2)); h.addSpacing(10); h.addWidget(ui.label(title, ui.mono(12)))
        h.addStretch(1); h.addWidget(ui.label('Ready' if num == '01' and self.mic else '', ui.mono(10), ui.G)); v.addLayout(h)
        v.addWidget(ui.label(text, ui.body(12), ui.G, wrap=True)); self.lay.addWidget(row)

    def add_pkg(self, num, pkg):
        row = QFrame(); row.setStyleSheet(f'QFrame {{ border-bottom:1px solid {ui.LINE}; }} QLabel {{ border:none; }}')
        v = QVBoxLayout(row); v.setContentsMargins(0, 14, 0, 14); v.setSpacing(6)
        h = QHBoxLayout(); h.addWidget(ui.label(num, ui.mono(11), ui.G2)); h.addSpacing(10); h.addWidget(ui.label(pkg['name'], ui.mono(12)))
        h.addStretch(1); state = ui.label(human(pkg['size']), ui.mono(10), ui.G); h.addWidget(state); v.addLayout(h)
        v.addWidget(ui.label(f"{pkg['why']} From {pkg['source']}.", ui.body(12), ui.G, wrap=True))
        bar = Bar(); v.addWidget(bar); bar.hide()
        self.rows[pkg['key']] = (state, bar)
        self.lay.addWidget(row)

    def no_gpu(self):
        self.want_gpu = False; self.build_list()

    def start(self):
        self.go.setEnabled(False); self.go.setText('Downloading'); self.skip_gpu.hide()
        for state, bar in self.rows.values():
            bar.show()
        self.worker = Downloader(self.packages)
        self.worker.progress.connect(self.on_progress)
        self.worker.finished_pkg.connect(self.on_pkg)
        self.worker.failed.connect(self.on_fail)
        self.worker.finished.connect(self.on_all)
        self.worker.start()

    def on_progress(self, key, done, total, speed):
        state, bar = self.rows[key]
        bar.set(done / max(1, total))
        eta = f' · {int((total - done) / speed // 60)}m {int((total - done) / speed % 60)}s left' if speed > 1 else ''
        state.setText(f'{human(done)} of {human(total)}{eta}')

    def on_pkg(self, key):
        state, bar = self.rows[key]; bar.set(1); state.setText('Done')

    def on_fail(self, message):
        self.note.setText(f'Download stopped: {message}  Press Start to resume where it left off.')
        self.go.setText('Start'); self.go.setEnabled(True)
        self.worker = None

    def on_all(self):
        if self.worker and model_ready(HOME):
            self.show_done()

    # ---- screen 2: you're in ------------------------------------------------------------------------------
    def show_done(self):
        self.page.hide(); self.page.setParent(None); self.page.deleteLater()
        self.page = QWidget(self); self.page.setGeometry(0, 40, 962, 582); self.page.show()
        ui.Headline("YOU'RE IN", 150, stretch=1.15, parent=self.page, live=lambda: None).move(44, 40)
        ui.label('Hold Ctrl+Win. Talk. Let go.', ui.mono(13), ui.W, self.page).move(48, 290)
        ui.label('It lives in your tray now. Close this window, it keeps running.', ui.mono(11), ui.G, self.page).move(48, 318)
        line = QFrame(self.page); line.setGeometry(48, 400, 866, 1); line.setStyleSheet(f'background:{ui.LINE};')
        ui.Headline('LIKE IT? SAY IT', 44, stop=False, parent=self.page).move(48, 430)
        ui.label('Free app. The only thing we ask is a follow.', ui.mono(10), ui.G, self.page).move(48, 490)
        follow = ui.Pill('Follow @nuffsaid.app', self.page); follow.move(640, 440)
        follow.setStyleSheet(f"QPushButton {{ color:{ui.K}; background:{ui.W}; border:1px solid {ui.W}; border-radius:13px; padding:0 16px; }}")
        follow.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(INSTAGRAM)))
        done = ui.Pill('Done', self.page); done.move(820, 440); done.clicked.connect(self.finish)
        for w in self.page.findChildren(QWidget):
            w.show()

    def finish(self):
        self.done.emit(True); self.close()

    def quit(self):
        if self.worker:
            self.worker.stop = True; self.worker.wait(3000)
        self.done.emit(model_ready(HOME)); self.close()


def run_setup(app):
    """Block until setup finishes. Returns True when the speech model is ready."""
    from PyQt6.QtCore import QEventLoop
    window = SetupWindow()
    result = {'ok': False}
    loop = QEventLoop()
    window.done.connect(lambda ok: (result.update(ok=ok), loop.quit()))
    window.show(); window.raise_(); window.activateWindow()
    loop.exec()
    return result['ok']
