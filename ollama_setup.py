"""One-click local cleanup: install Ollama and download a recommended model from inside NuffSaid.
Ollama (ollama.com, free, open source) runs the cleanup model on this PC. The installer comes from Ollama's official
download link and is only run if Windows confirms it is signed by Ollama. Models download through Ollama itself."""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from PyQt6.QtCore import QThread, pyqtSignal

BASE = 'http://127.0.0.1:11434'   # not localhost: that adds ~2 s per request on Windows
INSTALLER_URL = 'https://ollama.com/download/OllamaSetup.exe'
INSTALLED_EXE = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Programs' / 'Ollama' / 'ollama app.exe'

# Recommended models, picked from tools/bench_cleanup_models.py results (see cleanup-bench.json).
MODELS = [
    # (ollama name, display name, size in bytes, one-line description). Benchmark 2026-10-13: Qwen 2.5 3B with
    # examples cleaned 7/8 at 1.9 GB vs Llama 3 8B 8/8 at 4.7 GB; Llama 3.2 3B/1B and Gemma 3 4B were unreliable.
    ('qwen2.5:3b', 'Qwen 2.5 3B', 1_930_000_000, 'Recommended. Clean, fast, light on your PC.'),
    ('llama3:instruct', 'Llama 3 8B', 4_660_000_000, 'Best quality. Bigger, and heavier on your graphics card.'),
]
RECOMMENDED = MODELS[0][0]


def delete_model(name):
    try:
        return requests.delete(BASE + '/api/delete', json={'model': name}, timeout=30).status_code == 200
    except requests.RequestException:
        return False


def running():
    try:
        return requests.get(BASE + '/api/version', timeout=1.5).status_code == 200
    except requests.RequestException:
        return False


def installed():
    return running() or INSTALLED_EXE.is_file()


def start():
    """Start Ollama if it is installed but not running; wait up to 30 s for its server."""
    if running():
        return True
    if INSTALLED_EXE.is_file():
        subprocess.Popen([str(INSTALLED_EXE)], creationflags=0x08000000)
    for _ in range(60):
        if running():
            return True
        time.sleep(.5)
    return False


def local_models():
    try:
        return {m['name']: m.get('size', 0) for m in requests.get(BASE + '/api/tags', timeout=3).json().get('models', [])}
    except requests.RequestException:
        return {}


def installer_size():
    try:
        return int(requests.head(INSTALLER_URL, allow_redirects=True, timeout=10).headers.get('Content-Length', 0))
    except Exception:
        return 0


def human(n):
    return f'{n / 1e9:.1f} GB' if n >= 1e9 else f'{n / 1e6:.0f} MB'


class InstallOllama(QThread):
    progress = pyqtSignal(int, int)        # bytes done, total
    status = pyqtSignal(str)
    done = pyqtSignal(bool, str)

    def run(self):
        try:
            path = Path(tempfile.gettempdir()) / 'OllamaSetup.exe'
            with requests.get(INSTALLER_URL, stream=True, timeout=30) as r:
                r.raise_for_status()
                total, got = int(r.headers.get('Content-Length', 0)), 0
                with open(path, 'wb') as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk); got += len(chunk); self.progress.emit(got, total)
            self.status.emit('Checking the installer is signed by Ollama…')
            check = subprocess.run(['powershell', '-NoProfile', '-Command',
                                    f"$s = Get-AuthenticodeSignature -LiteralPath '{path}'; \"$($s.Status)|$($s.SignerCertificate.Subject)\""],
                                   capture_output=True, text=True, timeout=60, creationflags=0x08000000).stdout.strip()
            status, _, subject = check.partition('|')
            if status != 'Valid' or 'ollama' not in subject.lower():
                path.unlink(missing_ok=True)
                self.done.emit(False, "The download isn't signed by Ollama, so it wasn't run.")
                return
            self.status.emit('Installing Ollama…')
            subprocess.run([str(path), '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'], timeout=900, creationflags=0x08000000)
            path.unlink(missing_ok=True)
            self.status.emit('Starting Ollama…')
            ok = start()
            self.done.emit(ok, '' if ok else 'Ollama installed but did not start. Open it from the Start menu, then try again.')
        except Exception as exc:
            self.done.emit(False, f'Could not install Ollama: {exc}')


class PullModel(QThread):
    progress = pyqtSignal(int, int)
    done = pyqtSignal(bool, str)

    def __init__(self, name):
        super().__init__(); self.name = name

    def run(self):
        try:
            with requests.post(BASE + '/api/pull', json={'model': self.name, 'stream': True}, stream=True, timeout=60) as r:
                r.raise_for_status()
                layers = {}
                for line in r.iter_lines():
                    if not line:
                        continue
                    msg = json.loads(line)
                    if msg.get('error'):
                        raise RuntimeError(msg['error'])
                    if msg.get('digest') and msg.get('total'):
                        layers[msg['digest']] = (msg.get('completed', 0), msg['total'])
                        self.progress.emit(sum(c for c, _ in layers.values()), sum(t for _, t in layers.values()))
                    if msg.get('status') == 'success':
                        self.done.emit(True, ''); return
            self.done.emit(self.name in local_models(), '')
        except Exception as exc:
            self.done.emit(False, f'Download failed: {exc}')
