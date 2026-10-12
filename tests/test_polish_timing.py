import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from run_flow import DictationController, LLMPolisher, AppState

class PolishTimingTests(unittest.TestCase):
    def test_blob_exit_precedes_paste_without_waiting_for_restoration(self):
        events=[]
        obj=SimpleNamespace(_shutdown=False,_target_window=42,
            _hotkeys=Mock(),_desktop=SimpleNamespace(call=lambda fn:fn()),
            _tray=SimpleNamespace(set_state=lambda state:events.append(('overlay',state))),
            _paste=SimpleNamespace(paste_text=lambda text:events.append(('paste',text))))
        with patch('ctypes.windll.user32.GetForegroundWindow',return_value=42):
            DictationController._insert(obj,'Hello')
        self.assertEqual(events,[('overlay',AppState.IDLE),('paste','Hello')])

    def test_preload_is_empty_and_keeps_model_warm(self):
        polisher=LLMPolisher()
        polisher.backend='ollama'
        with patch('run_flow.requests.post') as post:
            polisher.preload()
        payload=post.call_args.kwargs['json']
        self.assertNotIn('prompt',payload)
        self.assertEqual(payload['keep_alive'],'15m')
        self.assertEqual(payload['model'],polisher.cfg['model'])
