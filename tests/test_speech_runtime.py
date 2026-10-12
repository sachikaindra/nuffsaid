import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from speech_runtime import AdaptiveSpeechEngine


class DeviceSelectionTests(unittest.TestCase):
    def test_long_recording_uses_conservative_decoding_without_text_deletion(self):
        model = Mock()
        model.transcribe.return_value = (iter([SimpleNamespace(text='Hold on. Hold on.')]), SimpleNamespace(language='en'))
        engine = self.engine(Mock(return_value=model))
        text, _ = engine.transcribe_text(object(), 'Iyas')
        opts = model.transcribe.call_args.kwargs
        self.assertFalse(opts['condition_on_previous_text'])
        self.assertEqual(opts['temperature'], 0.0)
        self.assertTrue(opts['word_timestamps'])
        self.assertEqual(opts['hallucination_silence_threshold'], 2.0)
        self.assertEqual(opts['initial_prompt'], 'Iyas')
        self.assertEqual(text, 'Hold on. Hold on.')

    def engine(self, factory=None, count=None, supported=None, **settings):
        cfg = dict(model='turbo', device='auto', compute_type='auto')
        cfg.update(settings)
        return AdaptiveSpeechEngine(cfg, Path('.'), model_factory=factory or Mock(),
            device_count=count or Mock(return_value=1),
            supported_types=supported or Mock(return_value={'float16', 'float32'}))

    def test_compatible_gpu_uses_float16(self):
        factory = Mock()
        engine = self.engine(factory)
        self.assertEqual((engine.device, engine.compute_type), ('cuda', 'float16'))
        self.assertEqual(factory.call_args.kwargs, dict(device='cuda', compute_type='float16'))

    def test_no_gpu_uses_cpu_without_gpu_precision(self):
        engine = self.engine(count=Mock(return_value=0), compute_type='float16')
        self.assertEqual((engine.device, engine.compute_type), ('cpu', 'int8'))

    def test_broken_driver_detection_uses_cpu(self):
        engine = self.engine(count=Mock(side_effect=RuntimeError('driver unavailable')))
        self.assertEqual(engine.device, 'cpu')
        self.assertIn('driver unavailable', engine.fallback_reason)

    def test_explicit_cpu_never_queries_gpu(self):
        count = Mock(side_effect=AssertionError('must not query CUDA'))
        engine = self.engine(count=count, device='cpu')
        self.assertEqual(engine.device, 'cpu')
        count.assert_not_called()

    def test_model_load_gpu_failure_falls_back(self):
        factory = Mock(side_effect=[RuntimeError('CUDA out of memory'), Mock()])
        engine = self.engine(factory)
        self.assertEqual(engine.device, 'cpu')
        self.assertEqual(factory.call_args.kwargs, dict(device='cpu', compute_type='int8'))
        self.assertIn('out of memory', engine.fallback_reason)

    def test_lazy_inference_failure_retries_original_audio(self):
        def broken_segments():
            raise RuntimeError('cuDNN failed')
            yield
        gpu, cpu = Mock(), Mock()
        gpu.transcribe.return_value = (broken_segments(), SimpleNamespace(language='en'))
        cpu.transcribe.return_value = (iter([SimpleNamespace(text='Recovered text')]), SimpleNamespace(language='en'))
        engine = self.engine(Mock(side_effect=[gpu, cpu]))
        audio = object()
        text, _ = engine.transcribe_text(audio, 'Priya')
        self.assertEqual(text, 'Recovered text')
        self.assertEqual(engine.device, 'cpu')
        self.assertIs(cpu.transcribe.call_args.args[0], audio)
        self.assertEqual(cpu.transcribe.call_args.kwargs['initial_prompt'], 'Priya')

    def test_warmup_exercises_decoder_without_vad(self):
        model = Mock()
        model.transcribe.return_value = (iter([]), SimpleNamespace(language='en'))
        engine = self.engine(Mock(return_value=model))
        engine.warmup()
        self.assertFalse(model.transcribe.call_args.kwargs['vad_filter'])

    def test_cpu_failure_propagates_without_retry_loop(self):
        model = Mock()
        model.transcribe.side_effect = RuntimeError('invalid model')
        factory = Mock(return_value=model)
        engine = self.engine(factory, device='cpu')
        with self.assertRaisesRegex(RuntimeError, 'invalid model'):
            engine.transcribe_text(object())
        self.assertEqual(factory.call_count, 1)

    def test_uses_bundled_model_without_download(self):
        with tempfile.TemporaryDirectory() as folder:
            model_dir = Path(folder) / 'models' / 'turbo'
            model_dir.mkdir(parents=True)
            factory = Mock()
            AdaptiveSpeechEngine(dict(model='turbo', device='cpu'), folder,
                model_factory=factory, device_count=Mock(), supported_types=Mock())
            self.assertEqual(factory.call_args.args[0], str(model_dir))
