import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from personal_store import PersonalStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'history.sqlite3'
        self.store = PersonalStore(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_persist_raw_before_cleanup_and_restore_after_restart(self):
        entry = self.store.save('uh hello hello', 'hello')
        self.store.update(entry, 'Hello.')
        reopened = PersonalStore(self.path)
        self.assertEqual(reopened.latest(), 'Hello.')
        self.assertEqual(reopened.entries()[0][3], 'uh hello hello')
        reopened.save('unrelated selection', 'Unrelated selection.', 'cleanup')
        self.assertEqual(reopened.latest(), 'Hello.')

    def test_retention(self):
        for i in range(205):
            self.store.save(str(i), str(i))
        self.assertEqual(len(self.store.entries()), 200)
        self.assertEqual(self.store.latest(), '204')

    def test_boundaries_unicode_longest_and_non_cascading(self):
        self.store.learn('john', 'Jon')
        self.store.learn('john smith', 'John Smythe')
        self.store.learn('Jon', 'Jonathan')
        self.store.learn('rene', 'René')
        self.assertEqual(self.store.apply('JOHN SMITH, john, johnson, rene.'),
                         'John Smythe, Jon, johnson, René.')
        self.assertIn('René', self.store.vocabulary_prompt())


class HotkeyTests(unittest.TestCase):
    def test_cleanup_letter_chord_triggers_once_on_release(self):
        from run_flow import HotkeyManager, keyboard, CONFIG
        self.assertEqual(CONFIG['hotkeys']['polish_trigger'], ['cmd', 'alt', 'e'])
        manager = HotkeyManager()
        cleanup = Mock()
        manager.add_binding(CONFIG['hotkeys']['polish_trigger'], on_release=cleanup)
        keys = [keyboard.Key.cmd, keyboard.Key.alt_l, keyboard.KeyCode.from_char('e')]
        for key in keys + [keys[-1]]:
            manager._on_p(key)
        cleanup.assert_not_called()
        for key in reversed(keys):
            manager._on_r(key)
        cleanup.assert_called_once()

    def test_once_per_chord_and_unrelated_release(self):
        from run_flow import HotkeyManager, keyboard
        manager = HotkeyManager()
        start, stop = Mock(), Mock()
        manager.add_binding(['ctrl', 'cmd'], start, stop)
        manager._on_p(keyboard.Key.ctrl_r)
        manager._on_p(keyboard.Key.cmd)
        manager._on_p(keyboard.Key.cmd)
        manager._on_p(keyboard.KeyCode.from_char('x'))
        manager._on_r(keyboard.KeyCode.from_char('x'))
        self.assertEqual(start.call_count, 1)
        self.assertEqual(stop.call_count, 0)
        manager._on_r(keyboard.Key.cmd)
        self.assertEqual(stop.call_count, 1)

    def test_no_match_on_missing_vk(self):
        from run_flow import HotkeyManager, keyboard
        manager = HotkeyManager()
        self.assertFalse(manager._matches([keyboard.KeyCode.from_char('1')], {keyboard.KeyCode.from_char('2')}))


class ProcessingTests(unittest.TestCase):
    def setUp(self):
        from run_flow import DictationController
        self.temp = tempfile.TemporaryDirectory()
        self.controller = DictationController.__new__(DictationController)
        self.controller._store = PersonalStore(Path(self.temp.name) / 'test.db')
        self.controller._store.learn('smyth', 'Smythe')
        self.controller._stt = Mock()
        self.controller._stt.transcribe.return_value.text = 'hello smyth'
        self.controller._polisher = Mock()
        self.controller._desktop = Mock()
        self.controller._tray = Mock()
        self.controller._insert = Mock()

    def tearDown(self):
        self.temp.cleanup()

    def test_cleanup_failure_keeps_dictation_and_inserts_original(self):
        import run_flow
        self.controller._polisher.polish.side_effect = RuntimeError('offline')
        with patch.dict(run_flow.CONFIG, {'enhancement': {'automatic': True}}):
            self.controller._process_dictation(Mock())
        self.controller._insert.assert_called_once_with('hello Smythe')
        self.assertEqual(self.controller._store.entries()[0][3], 'hello smyth')

    def test_paste_failure_preserves_history(self):
        import run_flow
        self.controller._insert.side_effect = RuntimeError('paste failed')
        with patch.dict(run_flow.CONFIG, {'enhancement': {'automatic': False}}):
            with self.assertRaises(RuntimeError):
                self.controller._process_dictation(Mock())
        self.assertEqual(self.controller._store.latest(), 'hello Smythe')

    def test_empty_and_truncated_llm_output_rejected(self):
        from run_flow import LLMPolisher
        polisher = LLMPolisher()
        polisher.backend = 'ollama'
        response = Mock()
        polisher._session = Mock()
        polisher._session.post.return_value = response
        for value in [{'response': ''}, {'response': 'Half a sentence', 'done_reason': 'length'}]:
            response.json.return_value = value
            with self.assertRaises(RuntimeError):
                polisher.polish('This is a complete sentence.')

    def test_known_model_preamble_removed(self):
        from run_flow import LLMPolisher
        polisher = LLMPolisher()
        polisher.backend = 'ollama'
        polisher._session = Mock()
        polisher._session.post.return_value.json.return_value = {'response': 'Here is the lightly copyedited text:\n\nHello, Priya. Good morning.'}
        self.assertEqual(polisher.polish('hello priya good morning').polished_text, 'Hello, Priya. Good morning.')


if __name__ == '__main__':
    unittest.main()
