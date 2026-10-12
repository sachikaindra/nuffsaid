import unittest
from cleanup_text import strip_preamble


class PreambleTests(unittest.TestCase):
    def test_lightly_cleaned_up_header(self):
        self.assertEqual(strip_preamble('Here is the lightly cleaned up text:\n\nOkay, continue.', 'Okay continue.'), 'Okay, continue.')
    def test_repeated_headers(self):
        self.assertEqual(strip_preamble('Here is the cleaned text:\n\nHere is the cleaned text:\r\nHello.', 'hello'), 'Hello.')

    def test_same_line_and_markdown(self):
        self.assertEqual(strip_preamble('**Here is the cleaned text:** Hello.', 'hello'), 'Hello.')

    def test_literal_source_preserved(self):
        source = 'Here is the cleaned text: Hello.'
        self.assertEqual(strip_preamble(source, source), source)
        self.assertEqual(strip_preamble('Here is the cleaned text:\n' + source, source), source)

    def test_body_mentions_preserved(self):
        source = 'It says Here is the cleaned text: each time.'
        self.assertEqual(strip_preamble(source, source), source)

    def test_header_only_becomes_empty(self):
        self.assertEqual(strip_preamble('Here is the cleaned text:', 'hello'), '')
