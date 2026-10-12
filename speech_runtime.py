"""Whisper device selection, packaged CUDA discovery, and CPU recovery."""
import gc
import importlib
import logging
import os
from pathlib import Path
import sys

_dll_handles = []
_dll_paths = set()


def configure_cuda_dlls():
    """Keep DLL-directory handles alive; closing them removes the search path."""
    if os.name != 'nt':
        return
    candidates = [Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'cuda']
    for package in ('nvidia.cublas', 'nvidia.cudnn', 'nvidia.cuda_runtime', 'nvidia.cuda_nvrtc'):
        try:
            module = importlib.import_module(package)
            candidates.extend(Path(path) / 'bin' for path in module.__path__)
        except ImportError:
            continue
    for folder in candidates:
        path = str(folder.resolve())
        if folder.is_dir() and path not in _dll_paths:
            _dll_handles.append(os.add_dll_directory(path))
            _dll_paths.add(path)
            os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')


class AdaptiveSpeechEngine:
    def __init__(self, config, app_dir, model_factory=None, device_count=None, supported_types=None):
        configure_cuda_dlls()
        if model_factory is None:
            from faster_whisper import WhisperModel
            model_factory = WhisperModel
        if device_count is None or supported_types is None:
            import ctranslate2
            device_count = device_count or ctranslate2.get_cuda_device_count
            supported_types = supported_types or ctranslate2.get_supported_compute_types
        self.cfg = dict(config)
        self._factory = model_factory
        self._model = None
        self.fallback_reason = ''
        self.model_name = self.cfg.get('model', 'turbo')
        self.model_path = self.model_name
        for candidate in (Path(app_dir) / self.model_name, Path(app_dir) / 'models' / self.model_name):
            if candidate.is_dir():
                self.model_path = str(candidate)
                break
        requested = self.cfg.get('device', 'auto')
        if requested not in ('auto', 'cpu', 'cuda'):
            raise ValueError('stt.device must be auto, cpu, or cuda')
        target = 'cpu'
        if requested != 'cpu':
            try:
                if device_count() > 0:
                    target = 'cuda'
                else:
                    self.fallback_reason = 'No compatible NVIDIA CUDA device found'
            except Exception as exc:
                self.fallback_reason = f'CUDA detection failed: {exc}'
        compute = self.cfg.get('compute_type', 'auto')
        if target == 'cuda':
            try:
                types = supported_types('cuda')
                if compute == 'auto':
                    compute = next(kind for kind in ('float16', 'int8_float32', 'float32') if kind in types)
                self._load(target, compute)
            except Exception as exc:
                self._fallback(exc)
        else:
            self._load('cpu', self._cpu_compute())
        logging.info('Speech engine: %s; fallback reason: %s', self.description, self.fallback_reason or 'none')

    def _cpu_compute(self):
        # Never carry a CUDA-only precision such as float16 into the CPU path.
        if self.cfg.get('device') == 'cpu' and self.cfg.get('compute_type') in ('int8', 'float32'):
            return self.cfg['compute_type']
        return self.cfg.get('cpu_compute_type', 'int8')

    def _load(self, device, compute):
        logging.info('Loading Whisper %s on %s (%s)', self.model_name, device, compute)
        self._model = self._factory(self.model_path, device=device, compute_type=compute)
        self.device, self.compute_type = device, compute

    def _fallback(self, error):
        self.fallback_reason = str(error)
        logging.warning('GPU recognition unavailable; retrying Whisper %s on CPU: %s', self.model_name, error)
        self._model = None
        gc.collect()
        self._load('cpu', self._cpu_compute())

    @property
    def description(self):
        device = 'NVIDIA GPU (CUDA)' if self.device == 'cuda' else 'CPU'
        return f'Whisper {self.model_name} — {device} — {self.compute_type}'

    def _decode(self, audio, options):
        def run():
            segments, info = self._model.transcribe(audio, **options)
            # Inference is lazy: failures can occur when consuming the generator.
            text = ' '.join(segment.text for segment in segments).strip()
            return text, info
        try:
            return run()
        except (RuntimeError, OSError) as exc:
            if self.device != 'cuda':
                raise
            self._fallback(exc)
            return run()  # Retry the same captured audio once; do not discard it.

    def transcribe_text(self, audio, initial_prompt=None):
        return self._decode(audio, dict(
            language=self.cfg.get('language', 'en'),
            beam_size=self.cfg.get('beam_size', 5),
            vad_filter=self.cfg.get('vad_filter', True),
            vad_parameters=self.cfg.get('vad_parameters'),
            initial_prompt=initial_prompt or None,
            # Do not feed generated text back into later audio windows: this can
            # propagate an invented phrase through a long recording.
            condition_on_previous_text=False,
            temperature=0.0,
            # Word alignment enables faster-whisper's built-in detection of
            # anomalous segments surrounded by silence. No phrase blacklists.
            word_timestamps=True,
            hallucination_silence_threshold=2.0,
        ))

    def warmup(self):
        import numpy as np
        # Disabling VAD forces real encoder/decoder execution and discovers
        # missing cuDNN DLLs before the first user recording.
        self._decode(np.zeros(16000, dtype=np.float32),
                     dict(language='en', vad_filter=False, beam_size=1))
        logging.info('Speech warmup passed: %s', self.description)
