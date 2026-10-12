"""Local recovery and explicit personal corrections. No audio is retained."""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager


class PersonalStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, created TEXT, kind TEXT, raw TEXT, output TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS corrections (wrong TEXT PRIMARY KEY COLLATE NOCASE, right TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, raw, output, kind='dictation'):
        with self.connect() as db:
            cursor = db.execute('INSERT INTO history(created,kind,raw,output) VALUES (?,?,?,?)',
                                (datetime.now(timezone.utc).isoformat(timespec='seconds'), kind, raw, output))
            db.execute('DELETE FROM history WHERE id NOT IN (SELECT id FROM history ORDER BY id DESC LIMIT 200)')
            return cursor.lastrowid

    def update(self, entry_id, output):
        with self.connect() as db:
            db.execute('UPDATE history SET output=? WHERE id=?', (output, entry_id))

    def entries(self):
        with self.connect() as db:
            return db.execute('SELECT id,created,kind,raw,output FROM history ORDER BY id DESC').fetchall()

    def latest(self):
        with self.connect() as db:
            row = db.execute("SELECT output FROM history WHERE kind='dictation' ORDER BY id DESC LIMIT 1").fetchone()
            return row[0] if row else ''

    def clear_history(self):
        with self.connect() as db:
            db.execute('DELETE FROM history')

    def corrections(self):
        with self.connect() as db:
            return dict(db.execute('SELECT wrong,right FROM corrections ORDER BY wrong').fetchall())

    def learn(self, wrong, right):
        wrong, right = wrong.strip(), right.strip()
        if not wrong or not right:
            raise ValueError('Both spellings are required.')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO corrections(wrong,right) VALUES (?,?)', (wrong, right))

    def forget(self, wrong):
        with self.connect() as db:
            db.execute('DELETE FROM corrections WHERE wrong=?', (wrong,))

    def apply(self, text):
        corrections = self.corrections()
        if not corrections:
            return text
        # A single pass prevents cascading replacements; longer phrases win.
        lookup = {key.casefold(): value for key, value in corrections.items()}
        pattern = r'(?<!\w)(?:' + '|'.join(re.escape(k) for k in sorted(corrections, key=len, reverse=True)) + r')(?!\w)'
        return re.sub(pattern, lambda match: lookup[match.group().casefold()], text, flags=re.IGNORECASE)

    def vocabulary_prompt(self):
        return ', '.join(dict.fromkeys(self.corrections().values()))[:1500]
