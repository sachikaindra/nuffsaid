"""Recovery and explicit vocabulary editing windows."""
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                            QTextEdit, QPushButton, QLabel, QInputDialog, QMessageBox)


class HistoryDialog(QDialog):
    def __init__(self, store, desktop):
        super().__init__()
        self.store, self.desktop = store, desktop
        self.setWindowTitle('NuffSaid history â€” last 200 entries, stored on this PC')
        self.resize(780, 600)
        layout = QVBoxLayout(self)
        self.list = QListWidget()
        layout.addWidget(self.list)
        self.raw = QTextEdit()
        self.output = QTextEdit()
        self.raw.setReadOnly(True)
        self.output.setReadOnly(True)
        layout.addWidget(QLabel('Original recognition'))
        layout.addWidget(self.raw)
        layout.addWidget(QLabel('Text prepared for insertion'))
        layout.addWidget(self.output)
        row = QHBoxLayout()
        for title, action in [('Copy original', lambda: desktop.set_text(self.raw.toPlainText())),
                              ('Copy output', lambda: desktop.set_text(self.output.toPlainText())),
                              ('Refresh', self.refresh), ('Clear history', self.clear)]:
            button = QPushButton(title)
            button.clicked.connect(action)
            row.addWidget(button)
        layout.addLayout(row)
        layout.addWidget(QLabel('Copy buttons deliberately replace the clipboard. Dictation preserves it.'))
        self.list.currentRowChanged.connect(self.select)
        self.refresh()

    def refresh(self):
        self.entries = self.store.entries()
        self.list.clear()
        for _, created, kind, raw, output in self.entries:
            self.list.addItem(f'{created}  [{kind}]  {output[:85]}')
        if self.entries:
            self.list.setCurrentRow(0)
        else:
            self.raw.clear()
            self.output.clear()

    def select(self, row):
        if 0 <= row < len(self.entries):
            self.raw.setPlainText(self.entries[row][3])
            self.output.setPlainText(self.entries[row][4])

    def clear(self):
        if QMessageBox.question(self, 'Clear history', 'Delete saved dictation history? Your dictionary will remain.') == QMessageBox.StandardButton.Yes:
            self.store.clear_history()
            self.refresh()


class DictionaryDialog(QDialog):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setWindowTitle('Personal dictionary')
        self.resize(600, 400)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('Save a misheard word or phrase and its correct spelling.\nCorrections apply to future dictations and guide recognition.\nThis does not monitor edits in other apps or train your voice.'))
        self.list = QListWidget()
        layout.addWidget(self.list)
        for title, action in [('Add / update correction', self.add), ('Remove selected', self.remove)]:
            button = QPushButton(title)
            button.clicked.connect(action)
            layout.addWidget(button)
        self.refresh()

    def refresh(self):
        self.words = list(self.store.corrections().items())
        self.list.clear()
        for wrong, right in self.words:
            self.list.addItem(f'{wrong}  â†’  {right}')

    def add(self):
        wrong, ok = QInputDialog.getText(self, 'Learn correction', 'Misheard spelling or phrase:')
        if not ok or not wrong.strip():
            return
        right, ok = QInputDialog.getText(self, 'Learn correction', 'Correct spelling or phrase:', text=wrong)
        if ok and right.strip():
            self.store.learn(wrong, right)
            self.refresh()

    def remove(self):
        row = self.list.currentRow()
        if row >= 0:
            self.store.forget(self.words[row][0])
            self.refresh()
