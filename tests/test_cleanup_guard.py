import unittest
from unittest.mock import Mock
from cleanup_text import validate_cleanup


class CleanupGuardTests(unittest.TestCase):
    def test_meaning_changes_rejected(self):
        for raw, output in [
            ('Wait for further feedback.', "I'll wait for further feedback."),
            ('I want it like how you edit.', 'I want it like how I edit.'),
            ('Are you not able to send messages?', 'Are you able to send messages?'),
            ('Okay, create a new carousel.', 'Create a new carousel.'),
            ('From the website', 'The text is already short. I will not make changes.'),
            ('Please adjust the dashboard colors.', 'Please adjust the dashboard colors. Note: filler words were removed and the meaning was preserved.'),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(validate_cleanup(raw, output), raw)

    def test_valid_cleanup_passes(self):
        for raw, output in [
            ('I I will send it you know tomorrow', "I'll send it tomorrow."),
            ('Okay um please check the file', 'Okay, please check the file.'),
            ('Number one check footage number two add captions', '· Check footage.\n· Add captions.'),
            ('I do not want that', "I don't want that."),
        ]:
            with self.subTest(raw=raw):
                self.assertEqual(validate_cleanup(raw, output), output)

    def test_fragments_skip_model_for_both_backends(self):
        from run_flow import LLMPolisher
        for backend in ['ollama', 'openrouter']:
            obj = LLMPolisher()
            obj.backend = backend
            obj._session = Mock()
            for source in ['Format', 'Quickly', 'from the website', 'Okay']:
                self.assertEqual(obj.polish(source).polished_text, source)
            obj._session.post.assert_not_called()

    def test_ollama_integration_rejects_perspective_change(self):
        from run_flow import LLMPolisher
        obj = LLMPolisher()
        obj.backend = 'ollama'
        obj._session = Mock()
        obj._session.post.return_value.json.return_value = {'response': 'It should look like how I edit.'}
        raw = 'It should look like how you edit.'
        self.assertEqual(obj.polish(raw).polished_text, raw)
