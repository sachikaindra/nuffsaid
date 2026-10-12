import unittest
from unittest.mock import Mock
import requests
from openrouter_cleanup import cleanup, protect, MODEL, without_em_dashes


class OpenRouterTests(unittest.TestCase):
    def test_unwanted_dashes_removed_without_changing_hyphenated_words(self):
        self.assertEqual(without_em_dashes('Keep it simple\u2014you know what I mean.'),
                         'Keep it simple. You know what I mean.')
        self.assertEqual(without_em_dashes('A well-known name'), 'A well-known name')
    def test_secret_roundtrip(self):
        encrypted = protect(b'test-not-a-real-key')
        self.assertNotIn(b'test-not-a-real-key', encrypted)
        self.assertEqual(protect(encrypted, decrypt=True), b'test-not-a-real-key')

    def test_free_only_request(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {'choices': [
            {'finish_reason': 'stop', 'message': {'content': 'Hello.'}}]}
        self.assertEqual(cleanup(session, 'fake-key', 'Hello', 'Edit')[0], 'Hello.')
        args = session.post.call_args.kwargs
        self.assertEqual(args['timeout'], (2, 60))
        self.assertEqual(args['json']['model'], MODEL)
        self.assertTrue(MODEL.endswith(':free'))
        self.assertEqual(args['json']['provider']['max_price'], {'prompt': 0, 'completion': 0, 'request': 0})
        self.assertFalse(args['json']['provider']['allow_fallbacks'])
        self.assertNotIn('models', args['json'])
        self.assertNotIn('plugins', args['json'])
        self.assertFalse(args['allow_redirects'])

    def test_failure_does_not_retry_paid(self):
        session = Mock()
        session.post.return_value.status_code = 429
        with self.assertRaises(RuntimeError):
            cleanup(session, 'fake-key', 'Hello', 'Edit')
        self.assertEqual(session.post.call_count, 1)

    def test_timeout_is_sanitized(self):
        session = Mock()
        session.post.side_effect = requests.Timeout('sensitive details')
        with self.assertRaisesRegex(RuntimeError, '^Online cleanup connection failed or timed out$'):
            cleanup(session, 'fake-key', 'Hello', 'Edit')

    def test_truncated_output_rejected(self):
        session = Mock()
        session.post.return_value.status_code = 200
        session.post.return_value.json.return_value = {'choices': [
            {'finish_reason': 'length', 'message': {'content': 'Partial'}}]}
        with self.assertRaises(RuntimeError):
            cleanup(session, 'fake-key', 'Hello', 'Edit')
