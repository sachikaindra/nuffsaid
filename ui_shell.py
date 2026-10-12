"""NuffSaid interface in the brand system: one window (Home, History, Dictionary, Blob, Settings) and the tray menu.
Black, #F6F6F6, greys; the red gel is the only colour and the full stop on every page title.
Fonts: Bueno (statements), Aktiv Grotesk (body), Space Mono (labels) from assets/fonts (agency-licensed, not in git);
falls back to system fonts when they are missing."""
import os
import sys
import winreg
from datetime import datetime, timezone
from pathlib import Path

import time
from PyQt6.QtCore import Qt, QPoint, QRectF, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QFontMetricsF, QPainter, QPixmap, QPen, QPainterPath
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QStackedWidget, QScrollArea, QFrame, QLineEdit, QSlider, QMenu, QWidgetAction, QMessageBox,
                             QDialog, QPlainTextEdit)

K, W, G, G2, LINE = '#000000', '#F6F6F6', '#8A8A8A', '#3a3a3a', '#1e1e1e'
FAM = {'display': 'Impact', 'body': 'Segoe UI', 'mono': 'Consolas'}


def load_fonts(app_dir):
    folder = Path(app_dir) / 'assets' / 'fonts'
    for path in sorted(folder.glob('*.*tf')) if folder.exists() else []:
        families = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(path)))
        if not families:
            continue
        name = path.name.lower()
        key = 'display' if name.startswith('bueno') else 'body' if name.startswith('aktiv') else 'mono' if 'spacemono' in name else None
        if key:
            FAM[key] = families[0]


def _clean(f):
    f.setStyleStrategy(QFont.StyleStrategy.NoSubpixelAntialias)
    return f


def mono(px, bold=False):
    f = _clean(QFont(FAM['mono'])); f.setPixelSize(px); f.setBold(bold)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 106)
    return f


def body(px, weight=QFont.Weight.Normal):
    f = _clean(QFont(FAM['body'])); f.setPixelSize(px); f.setWeight(weight)
    return f


def display(px):
    f = _clean(QFont(FAM['display'])); f.setPixelSize(px); f.setWeight(QFont.Weight.Black)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    return f


def qss():
    return f"""
    QWidget {{ color:{W}; }}
    QMenu {{ background:#0a0a0a; border:1px solid #262626; border-radius:10px; padding:10px 0; }}
    QMenu::item {{ padding:9px 20px; color:{W}; background:transparent; }}
    QMenu::item:selected {{ background:#161616; }}
    QMenu::item:disabled {{ color:{G}; }}
    QMenu::separator {{ height:1px; background:{LINE}; margin:6px 0; }}
    QDialog, QMessageBox, QInputDialog {{ background:{K}; }}
    QLineEdit, QComboBox {{ background:transparent; border:none; border-bottom:1px solid {G2}; padding:7px 0; font-size:14px; selection-background-color:#333; }}
    QLineEdit:focus {{ border-bottom-color:{W}; }}
    QComboBox QAbstractItemView {{ background:#0a0a0a; border:1px solid #262626; selection-background-color:#1a1a1a; }}
    QPushButton {{ background:transparent; border:1px solid {G2}; border-radius:5px; padding:8px 16px; }}
    QPushButton:hover {{ border-color:{W}; }}
    QScrollArea, QScrollArea > QWidget > QWidget {{ background:transparent; border:none; }}
    QScrollBar:vertical {{ background:transparent; width:6px; margin:0; }}
    QScrollBar::handle:vertical {{ background:#2a2a2a; border-radius:3px; min-height:30px; }}
    QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ background:none; height:0; }}
    QSlider::groove:horizontal {{ height:2px; background:{G2}; }}
    QSlider::sub-page:horizontal {{ background:{W}; }}
    QSlider::handle:horizontal {{ background:{W}; width:14px; height:14px; margin:-6px 0; border-radius:7px; }}
    QToolTip {{ background:#0a0a0a; color:{W}; border:1px solid #262626; }}
    """


def apply(app, app_dir):
    """Load the brand fonts and style the whole app (dialogs included)."""
    load_fonts(app_dir)
    app.setFont(body(13))
    app.setStyleSheet(qss())


# --- The gel, rendered with the app's own shader (gel_renderer.py) -------------------------------------------
_GEL = {}


def gel_pixmap(diameter):
    """Pixmap whose visible blob is `diameter` px across (canvas is 1.72x, like the web full stop)."""
    diameter = max(6, int(diameter))
    if diameter in _GEL:
        return _GEL[diameter]
    side = int(diameter * 1.72)
    pm = None
    try:
        from gel_renderer import GelRenderer
        renderer = GelRenderer()
        pixels = max(64, side * 2)
        image = renderer.render(pixels, 1.4, .087, 0., 1 / 1.08, .25)
        renderer.close()
        pm = QPixmap.fromImage(image)
        pm.setDevicePixelRatio(pixels / side)
    except Exception:
        # No usable OpenGL: draw the pre-rendered gel (assets/gel.png), or a red dot if even that is missing.
        pm = QPixmap(side * 2, side * 2); pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = diameter
        art = QPixmap(str(Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'gel.png'))
        from liquid_overlay import sprites_available, paint_gel_sprite
        if sprites_available():
            k = side  # sprite canvas = 1.72 x the blob, same framing as the shader render
            paint_gel_sprite(p, QRectF(0, 0, 2 * k, 2 * k), 1.4, 0., 0.)
        elif not art.isNull():
            p.drawPixmap(QRectF(side - r, side - r, 2 * r, 2 * r), art, QRectF(art.rect()))
        else:
            p.setBrush(QColor(237, 36, 56)); p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QRectF(side - r, side - r, 2 * r, 2 * r))
        p.end()
        pm.setDevicePixelRatio(2)
    _GEL[diameter] = pm
    return pm


class LiveGel:
    """The overlay's motion (speech_motion.FluidMotion) driving the app shader, shared by every visible headline."""
    _renderer, _motion, _last, _frame = None, None, 0., {}
    held = 0          # keycaps currently pressed on Home: the gel 'talks' while they are held
    _pace, _next = .4, 0.

    @classmethod
    def frame(cls, side, sample_fn):
        from speech_motion import FluidMotion, MotionSample
        now = time.monotonic()
        if cls._motion is None:
            cls._motion, cls._last = FluidMotion(), now
        if now - cls._last > .005:
            sample = MotionSample()
            if cls.held:
                if now > cls._next:
                    import random
                    cls._pace, cls._next = .75 + random.random() * .25, now + .12 + random.random() * .15
                sample = MotionSample(True, cls._pace, now)
            try:
                got = sample_fn() if sample_fn else None
                if not cls.held and isinstance(got, MotionSample) and now - got.updated_at <= .35:
                    sample = got
            except Exception:
                pass
            steps = 2 if cls.held else 1      # keys held: the gel runs at double speed
            for _ in range(steps):
                cls._motion.advance(now - cls._last, sample)
            cls._last = now
            cls._frame = {}
        if side in cls._frame:
            return cls._frame[side]
        m = cls._motion
        pixels = max(64, min(512, side * 2))
        if cls._renderer is False:   # no usable OpenGL on this PC: real-gel frames instead
            return cls._sprite(side, m)
        try:
            if cls._renderer is None:
                from gel_renderer import GelRenderer
                cls._renderer = GelRenderer()
            if not getattr(cls, '_probed', False):   # one probe: raises when this PC renders empty
                cls._renderer.render(64, m.phase, m.deformation, 0., 1 / 1.08, 0.)
                cls._probed = True
        except Exception:
            cls._renderer = False
            return cls._sprite(side, m)
        from liquid_overlay import GLOW
        glow = m.activity * GLOW   # same halo as the dictation blob
        pm = QPixmap.fromImage(cls._renderer.render(pixels, m.phase, m.deformation, 0., 1 / 1.08, glow))
        pm.setDevicePixelRatio(pixels / side)
        cls._frame[side] = pm
        return pm


def _sprite_frame(side, phase, activity):
    from liquid_overlay import sprites_available, paint_gel_sprite
    if not sprites_available():
        raise RuntimeError('no gel frames')
    pm = QPixmap(side * 2, side * 2); pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    paint_gel_sprite(p, QRectF(0, 0, side * 2, side * 2), phase, activity, 0.)
    p.end(); pm.setDevicePixelRatio(2)
    return pm


LiveGel._sprite = classmethod(lambda cls, side, m: cls._frame.setdefault(('s', side), _sprite_frame(side, m.phase, m.activity)))


class Headline(QWidget):
    """A Bueno statement with the gel as its full stop. `stretch` scales the letters vertically, never the gel.
    With `live` (a motion-sample function) the gel moves like the overlay blob while the headline is visible."""
    def __init__(self, text, px, stretch=1.0, stop=True, parent=None, live=None):
        super().__init__(parent)
        self.text, self.px, self.stretch, self.stop, self.live = text, px, stretch, stop, live
        self.timer = QTimer(self); self.timer.setInterval(33); self.timer.timeout.connect(self.update)
        self.font_ = display(px)
        m = QFontMetricsF(self.font_)
        self.advance = m.horizontalAdvance(text)
        self.cap = m.capHeight()
        d = px * .3
        room = d * .8 if (live is not None and stop) else 0   # space for the bloom below the baseline
        self.setFixedSize(int(self.advance + (d * 1.6 if stop else 0) + 6), int(self.cap * stretch + px * .08 + room) + 4)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing); p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        base = self.cap * self.stretch + 2
        p.save(); p.translate(0, base); p.scale(1, self.stretch)
        p.setFont(self.font_); p.setPen(QColor(W)); p.drawText(QPoint(0, 0), self.text); p.restore()
        if self.stop:
            d = self.px * .3
            pm = None
            if self.live is not None:
                try:
                    pm = LiveGel.frame(int(d * 1.72), self.live)
                except Exception:
                    self.live = None
            pm = pm or gel_pixmap(d)
            side = pm.width() / pm.devicePixelRatio()
            cx, cy = self.advance - self.px * .015 + d / 2, base - d / 2
            if self.live is not None and LiveGel._motion is not None:
                from liquid_overlay import paint_bloom
                paint_bloom(p, cx, cy, d, LiveGel._motion.activity)
            p.drawPixmap(QRectF(cx - side / 2, cy - side / 2, side, side), pm, QRectF(pm.rect()))
        p.end()

    def showEvent(self, event):
        if self.live is not None and self.stop:
            self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)


def label(text, font, color=W, parent=None, wrap=False):
    lab = QLabel(text, parent); lab.setFont(font); lab.setStyleSheet(f'color:{color}; background:transparent;')
    lab.setWordWrap(wrap)
    return lab


class Link(QPushButton):
    def __init__(self, text, color=W, parent=None):
        super().__init__(text, parent)
        self.setFont(mono(10)); self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFlat(True)
        self.setStyleSheet(f"QPushButton {{ border:none; padding:2px 0; color:{color}; background:transparent; }} QPushButton:hover {{ color:{W}; }}")


class Toggle(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, on=False, parent=None):
        super().__init__(parent)
        self.on = on; self.setFixedSize(38, 20); self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_on(self, value):
        self.on = bool(value); self.update()

    def mousePressEvent(self, event):
        self.on = not self.on; self.update(); self.toggled.emit(self.on)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(.5, .5, 37, 19)
        if self.on:
            p.setBrush(QColor(W)); p.setPen(QPen(QColor(W), 1)); p.drawRoundedRect(r, 9.5, 9.5)
            p.setBrush(QColor(K)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QRectF(21, 4, 12, 12))
        else:
            p.setBrush(Qt.BrushStyle.NoBrush); p.setPen(QPen(QColor(G2), 1)); p.drawRoundedRect(r, 9.5, 9.5)
            p.setBrush(QColor(G)); p.setPen(Qt.PenStyle.NoPen); p.drawEllipse(QRectF(4, 4, 12, 12))
        p.end()


class Pill(QPushButton):
    """Small outlined action button for settings rows (Test, Change, Open)."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFont(mono(10)); self.setCursor(Qt.CursorShape.PointingHandCursor); self.setFixedHeight(26)
        self.setStyleSheet(f"QPushButton {{ color:{W}; background:transparent; border:1px solid {G2}; border-radius:13px; padding:0 12px; }}"
                           f" QPushButton:hover {{ border-color:{W}; }} QPushButton:pressed {{ background:{W}; color:{K}; }}")


class Row(QWidget):
    """Title + subtitle on the left (full width), a control in a fixed right column, a hairline below."""
    def __init__(self, title, subtitle, control, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(72)
        lay = QHBoxLayout(self); lay.setContentsMargins(0, 14, 0, 14); lay.setSpacing(18)
        text = QVBoxLayout(); text.setSpacing(4)
        text.addWidget(label(title, body(14)))
        self.sub = label(subtitle, body(12), G, wrap=True)
        text.addWidget(self.sub)
        lay.addLayout(text, 1)
        slot = QHBoxLayout(); slot.addStretch(1); slot.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        holder = QWidget(); holder.setFixedWidth(84); holder.setLayout(slot); slot.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(holder, 0, Qt.AlignmentFlag.AlignVCenter)

    def paintEvent(self, event):
        p = QPainter(self); p.setPen(QColor(LINE)); p.drawLine(0, self.height() - 1, self.width(), self.height() - 1); p.end()


class KeyCap(QPushButton):
    """Ctrl / Win on Home: press them for fun. They sink in, fill white, and the gel talks while held."""
    def __init__(self, text):
        super().__init__(text)
        self.setFont(mono(14)); self.setFixedHeight(44); self.setMinimumWidth(64)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""QPushButton {{ color:{W}; background:transparent; border:1px solid {W}; border-bottom:4px solid {W};
                                border-radius:6px; padding:0 14px 0 14px; margin-top:0; }}
                              QPushButton:pressed {{ color:{K}; background:{W}; border-bottom:1px solid {W}; margin-top:3px; }}""")
        self.pressed.connect(self.down); self.released.connect(self.up)

    def down(self):
        LiveGel.held += 1

    def up(self):
        LiveGel.held = max(0, LiveGel.held - 1)


def keycap(text):
    return KeyCap(text)


def local_time(created):
    try:
        return datetime.fromisoformat(created).astimezone()
    except Exception:
        return None


# --- Pages -------------------------------------------------------------------------------------------------------
class Page(QWidget):
    def __init__(self, title, hooks):
        super().__init__()
        self.hooks = hooks
        self.head = Headline(title, 96, parent=self, live=hooks.get('motion', lambda: None))
        self.head.move(44, 34)

    def refresh(self):
        pass


class HomePage(Page):
    def __init__(self, hooks):
        QWidget.__init__(self)
        self.hooks = hooks
        self.status_label = label('Status · listening for Ctrl+Win', mono(10), G, self); self.status_label.move(44, 34)
        self.engine = label('', mono(10), G, self); self.engine.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.engine.setGeometry(380, 30, 356, 54)
        Headline('READY', 232, stretch=1.18, parent=self, live=hooks.get('motion', lambda: None)).move(38, 84)
        self.update_btn = Pill('', self); self.update_btn.hide()
        self.update_btn.setStyleSheet(f"QPushButton {{ color:{K}; background:{W}; border:1px solid {W}; border-radius:13px; padding:0 14px; }}")
        keys = QWidget(self); lay = QHBoxLayout(keys); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(12)
        lay.addWidget(keycap('Ctrl')); lay.addWidget(label('+', mono(13), G)); lay.addWidget(keycap('Win'))
        lay.addSpacing(14); lay.addWidget(label('Hold. Talk. Let go.', mono(13)))
        keys.move(44, 418)
        self.count = label('0', display(64), W, self); self.count.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.count.setGeometry(456, 396, 280, 70)
        sub = label('Words said today\n0 typed', mono(10), G, self); sub.setAlignment(Qt.AlignmentFlag.AlignRight)
        sub.setGeometry(456, 468, 280, 34)
        grid = QWidget(self); g = QGridLayout(grid); g.setContentsMargins(0, 0, 0, 0); g.setHorizontalSpacing(24)
        for i, (k, d) in enumerate([('Double-tap Ctrl+Win', 'Hands-free. Ctrl+Win again to stop.'),
                                    ('Select text + Win+Alt+E', 'Cleans it up. Nothing selected?\nCleans your last dictation.'),
                                    ('Win+Alt+S', 'Paste the last one again.')]):
            g.addWidget(label(k, mono(10, True)), 0, i); g.addWidget(label(d, mono(10), G), 1, i, Qt.AlignmentFlag.AlignTop)
        grid.setGeometry(44, 500, 692, 76)

    def refresh(self):
        self.engine.setText(self.hooks['engine']().replace(' — ', '\n'))
        today, words = datetime.now().date(), 0
        for _, created, kind, raw, output in self.hooks['store'].entries():
            t = local_time(created)
            if t and t.date() == today and kind == 'dictation':
                words += len((output or '').split())
        self.count.setText(f'{words:,}')


class HistoryPage(Page):
    def __init__(self, hooks):
        super().__init__('SAID', hooks)
        info = label('Last 200 · stored on this PC', mono(10), G, self); info.setAlignment(Qt.AlignmentFlag.AlignRight)
        info.setGeometry(436, 52, 300, 20)
        clear = Link('Clear all', W, self); clear.move(686, 74); clear.clicked.connect(self.clear)
        self.scroll = QScrollArea(self); self.scroll.setWidgetResizable(True); self.scroll.setGeometry(44, 146, 700, 420)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def refresh(self):
        box = QWidget(); lay = QVBoxLayout(box); lay.setContentsMargins(0, 0, 8, 0); lay.setSpacing(0)
        entries = self.hooks['store'].entries()
        if not entries:
            lay.addWidget(label('Nothing said yet. Hold Ctrl+Win and talk.', body(14), G))
        for _, created, kind, raw, output in entries:
            t = local_time(created)
            row = QFrame(); row.setStyleSheet(f'QFrame {{ border-bottom:1px solid {LINE}; }} QLabel {{ border:none; }}')
            r = QGridLayout(row); r.setContentsMargins(0, 14, 0, 14); r.setHorizontalSpacing(20)
            stamp = (t.strftime('%H:%M') if t and t.date() == datetime.now().date() else t.strftime('%d %b') if t else '')
            r.addWidget(label(stamp, mono(10), G), 0, 0, Qt.AlignmentFlag.AlignTop)
            text = QVBoxLayout(); text.setSpacing(6)
            text.addWidget(label(output or raw or '', body(14), W, wrap=True))
            if raw and output and raw.strip() != output.strip():
                text.addWidget(label('Original', mono(9), G2)); text.addWidget(label(raw, body(13), G, wrap=True))
            r.addLayout(text, 0, 1)
            acts = QHBoxLayout(); acts.setSpacing(14)
            copy = Link('Copy', G); copy.clicked.connect(lambda _=False, s=output or raw: self.hooks['copy'](s))
            acts.addWidget(copy)
            if kind != 'dictation':
                acts.addWidget(label(kind, mono(9), G2))
            r.addLayout(acts, 0, 2, Qt.AlignmentFlag.AlignTop)
            r.setColumnMinimumWidth(0, 56); r.setColumnStretch(1, 1)
            lay.addWidget(row)
        lay.addStretch(1)
        self.scroll.setWidget(box)

    def clear(self):
        box = QMessageBox(QMessageBox.Icon.NoIcon, 'Clear history', 'Delete saved dictation history? Your dictionary stays.',
                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, self)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self.hooks['store'].clear_history(); self.refresh()


class DictionaryPage(Page):
    def __init__(self, hooks):
        super().__init__('SAY IT RIGHT', hooks)
        info = label('Fixes future dictations.\nNothing gets trained.', mono(10), G, self); info.setAlignment(Qt.AlignmentFlag.AlignRight)
        info.setGeometry(486, 44, 250, 40)
        head = QWidget(self); h = QGridLayout(head); h.setContentsMargins(0, 0, 0, 8)
        h.addWidget(label('We heard', mono(10), G), 0, 0); h.addWidget(label('You meant', mono(10), G), 0, 2)
        h.setColumnStretch(0, 1); h.setColumnMinimumWidth(1, 40); h.setColumnStretch(2, 1); h.setColumnMinimumWidth(3, 60)
        head.setGeometry(44, 146, 692, 26)
        self.scroll = QScrollArea(self); self.scroll.setWidgetResizable(True); self.scroll.setGeometry(44, 174, 700, 316)
        add = QWidget(self); a = QGridLayout(add); a.setContentsMargins(0, 0, 0, 0)
        self.wrong, self.right = QLineEdit(), QLineEdit()
        self.wrong.setPlaceholderText('What it typed'); self.right.setPlaceholderText('What you said')
        btn = Link('Add', W); btn.clicked.connect(self.add)
        for field in (self.wrong, self.right):
            field.returnPressed.connect(self.add)
        a.addWidget(self.wrong, 0, 0); a.addWidget(label('→', mono(12), G2), 0, 1, Qt.AlignmentFlag.AlignCenter)
        a.addWidget(self.right, 0, 2); a.addWidget(btn, 0, 3, Qt.AlignmentFlag.AlignRight)
        a.setColumnStretch(0, 1); a.setColumnMinimumWidth(1, 40); a.setColumnStretch(2, 1); a.setColumnMinimumWidth(3, 60)
        add.setGeometry(44, 500, 692, 44)
        self.error = label('', mono(9), G, self); self.error.setGeometry(44, 548, 692, 18)

    def refresh(self):
        box = QWidget(); lay = QVBoxLayout(box); lay.setContentsMargins(0, 0, 8, 0); lay.setSpacing(0)
        words = self.hooks['store'].corrections()
        if not words:
            lay.addWidget(label('Add a word it keeps getting wrong. Names, brands, places.', body(14), G))
        for wrong, right in words.items():
            row = QFrame(); row.setStyleSheet(f'QFrame {{ border-bottom:1px solid {LINE}; }} QLabel {{ border:none; }}')
            r = QGridLayout(row); r.setContentsMargins(0, 12, 0, 12)
            r.addWidget(label(wrong, body(14), G), 0, 0); r.addWidget(label('→', mono(12), G2), 0, 1, Qt.AlignmentFlag.AlignCenter)
            r.addWidget(label(right, body(14)), 0, 2)
            rm = Link('Delete', G2); rm.clicked.connect(lambda _=False, w=wrong: (self.hooks['store'].forget(w), self.refresh()))
            r.addWidget(rm, 0, 3, Qt.AlignmentFlag.AlignRight)
            r.setColumnStretch(0, 1); r.setColumnMinimumWidth(1, 40); r.setColumnStretch(2, 1); r.setColumnMinimumWidth(3, 60)
            lay.addWidget(row)
        lay.addStretch(1)
        self.scroll.setWidget(box)

    def add(self):
        try:
            self.hooks['store'].learn(self.wrong.text(), self.right.text())
            self.wrong.clear(); self.right.clear(); self.error.setText(''); self.refresh(); self.wrong.setFocus()
        except ValueError as exc:
            self.error.setText(str(exc))


class BlobPage(Page):
    def __init__(self, hooks):
        super().__init__('THE BLOB', hooks)
        label('It shows up when you talk. Drag it anywhere.', mono(10), G, self).move(44, 128)
        self.preview = QLabel(self); self.preview.setGeometry(44, 170, 400, 330)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f'background:#070707; border:1px solid {LINE}; border-radius:8px;')
        side = QWidget(self); s = QVBoxLayout(side); s.setContentsMargins(0, 0, 0, 0); s.setSpacing(0)
        side.setGeometry(480, 170, 256, 340)
        s.addWidget(label('Style', mono(10), G)); s.addSpacing(10)
        seg = QWidget(); sl = QHBoxLayout(seg); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)
        self.liquid, self.bar = QPushButton('Liquid blob'), QPushButton('Bottom bar')
        for b, v in ((self.liquid, True), (self.bar, False)):
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.clicked.connect(lambda _=False, v=v: self.set_style(v)); sl.addWidget(b)
        s.addWidget(seg); s.addSpacing(28)
        top = QHBoxLayout(); top.addWidget(label('Size', mono(10), G)); top.addStretch(1)
        self.size_label = label('', mono(10)); top.addWidget(self.size_label); s.addLayout(top); s.addSpacing(8)
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.setRange(24, 120); self.slider.valueChanged.connect(self.resize_blob)
        s.addWidget(self.slider); s.addSpacing(18)
        self.drag = Pill('Move'); self.drag.clicked.connect(self.toggle_drag)
        reset = Pill('Reset'); reset.clicked.connect(self.reset)
        s.addWidget(Row('Position', 'Anywhere on screen.', self.drag))
        s.addWidget(Row('Back to default', 'Bottom centre.', reset))
        s.addStretch(1)

    def hud(self):
        return self.hooks['hud']()

    def refresh(self):
        hud = self.hud()
        if not hud:
            return
        self.slider.blockSignals(True); self.slider.setValue(int(hud.settings['size'])); self.slider.blockSignals(False)
        self.paint_style(bool(hud.settings['enabled'])); self.paint_preview()

    def paint_style(self, liquid):
        on = f'background:{W}; color:{K}; border:1px solid {W};'
        off = f'background:transparent; color:{G}; border:1px solid {G2};'
        self.liquid.setStyleSheet(f'QPushButton {{ {on if liquid else off} border-top-left-radius:6px; border-bottom-left-radius:6px; border-top-right-radius:0; border-bottom-right-radius:0; padding:10px; }}')
        self.bar.setStyleSheet(f'QPushButton {{ {off if liquid else on} border-top-right-radius:6px; border-bottom-right-radius:6px; border-top-left-radius:0; border-bottom-left-radius:0; padding:10px; }}')

    def paint_preview(self):
        size = self.slider.value()
        self.size_label.setText(f'{size} px')
        hud = self.hud()
        if hud and not hud.settings.get('enabled', True):
            # Bottom bar: a mock screen with the bar glowing at its foot, as it looks while you talk.
            from liquid_overlay import paint_bar
            pm = QPixmap(796, 656); pm.setDevicePixelRatio(2); pm.fill(QColor('#070707'))
            p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(QColor('#1c1c1c'))
            for i in range(7):
                p.drawLine(28, 40 + i * 22, 28 + (300 if i % 3 else 200), 40 + i * 22)
            paint_bar(p, 398, 300, 2.2, 1.0)
            p.end()
            self.preview.setPixmap(pm)
            self.slider.setEnabled(False)
        else:
            self.preview.setPixmap(gel_pixmap(size))
            self.slider.setEnabled(True)

    def set_style(self, liquid):
        hud = self.hud()
        if hud:
            hud.change('enabled', liquid)
        self.paint_style(liquid)
        self.paint_preview()

    def resize_blob(self, value):
        hud = self.hud()
        if hud:
            hud.change('size', value); hud.place(); hud.update()
        self.paint_preview()

    def toggle_drag(self):
        hud = self.hud()
        if not hud:
            return
        editing = not getattr(hud, 'editing', False)
        hud.edit(editing)
        self.drag.setText('Done' if editing else 'Move')

    def reset(self):
        hud = self.hud()
        if hud:
            hud.settings.update(screen=QApplication.primaryScreen().name(), x=.5, y=1.); hud.place(); hud.save()

    def leave(self):
        hud = self.hud()
        if hud and getattr(hud, 'editing', False):
            hud.edit(False); self.drag.setText('Move')


RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'


def startup_command():
    if getattr(sys, 'frozen', False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    script = Path(__file__).with_name('run_flow.py')
    return f'"{pythonw}" "{script}"' + (' --local-install' if '--local-install' in sys.argv else '')


def starts_with_windows():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, 'NuffSaid')
            return True
    except OSError:
        return False


def set_start_with_windows(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, 'NuffSaid', 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, 'NuffSaid')
            except OSError:
                pass


class SettingsPage(Page):
    def __init__(self, hooks):
        super().__init__('SETTINGS', hooks)
        grid = QWidget(self); g = QHBoxLayout(grid); g.setContentsMargins(0, 0, 0, 0); g.setSpacing(44)
        grid.setGeometry(44, 146, 692, 396)
        left, right = QVBoxLayout(), QVBoxLayout()
        for col in (left, right):
            col.setSpacing(0)
        left.addWidget(label('Listening', mono(10), G)); left.addSpacing(4)
        test = Pill('Test'); test.clicked.connect(hooks['test_mic'])
        left.addWidget(Row('Microphone', 'Your default microphone. Test records 2 seconds.', test))
        model = Pill('Change'); model.clicked.connect(lambda: (hooks['choose_model'](), self.refresh()))
        self.model_row = Row('Speech model', '', model); left.addWidget(self.model_row)
        self.startup = Toggle(starts_with_windows()); self.startup.toggled.connect(self.set_startup)
        left.addWidget(Row('Start with Windows', 'Ready before you are.', self.startup))
        self.open_launch = Toggle(hooks['open_on_launch']()); self.open_launch.toggled.connect(hooks['set_open_on_launch'])
        left.addWidget(Row('Open dashboard on launch', 'Off = starts quietly in your tray.', self.open_launch))
        self.updates = Toggle(hooks.get('updates_on', lambda: True)()); self.updates.toggled.connect(hooks.get('set_updates_on', lambda v: None))
        left.addWidget(Row('Check for updates', 'Asks GitHub once a day. Sends nothing about you.', self.updates)); left.addStretch(1)
        right.addWidget(label('Cleanup', mono(10), G)); right.addSpacing(4)
        self.cleanup = Toggle(hooks['cleanup_on']()); self.cleanup.toggled.connect(lambda v: hooks['toggle_cleanup']())
        right.addWidget(Row('Auto cleanup', 'Fixes ums and punctuation.\nFirst one after launch is slower.\nOff = instant paste.', self.cleanup))
        prompt = Pill('Edit'); prompt.clicked.connect(self.edit_prompt)
        self.prompt_row = Row('Cleanup prompt', '', prompt); right.addWidget(self.prompt_row)
        engine = Pill('Change'); engine.clicked.connect(self.edit_engine)
        self.engine_row = Row('Cleanup engine', '', engine); right.addWidget(self.engine_row)
        cfg = Pill('Open'); cfg.clicked.connect(hooks['open_config'])
        right.addWidget(Row('Settings file', 'For people who like YAML.', cfg)); right.addStretch(1)
        g.setSpacing(48); g.addLayout(left, 1); g.addLayout(right, 1)
        label(f"NuffSaid {hooks.get('version', '1.0')} · free · nuffsaid.pages.dev", mono(10), G2, self).move(44, 548)
        quit_ = Link('Quit NuffSaid', G, self); quit_.move(640, 544); quit_.clicked.connect(hooks['quit'])

    def set_startup(self, value):
        try:
            set_start_with_windows(value)
        except OSError:
            self.startup.set_on(starts_with_windows())

    def refresh(self):
        self.model_row.sub.setText(self.hooks['engine']())
        self.engine_row.sub.setText(self.hooks['cleanup_desc']())
        self.cleanup.set_on(self.hooks['cleanup_on']())
        self.startup.set_on(starts_with_windows())
        self.open_launch.set_on(self.hooks['open_on_launch']())
        self.updates.set_on(self.hooks.get('updates_on', lambda: True)())
        custom = self.hooks['get_prompt']().strip() != self.hooks['default_prompt']().strip()
        self.prompt_row.sub.setText('Yours. Reset to ours anytime.' if custom else 'Ours: removes ums and repeats. Make it yours.')

    def edit_engine(self):
        dialog = EngineDialog(self.hooks, self.window())
        dialog.exec()
        self.refresh()

    def edit_prompt(self):
        dialog = PromptDialog(self.hooks['get_prompt'](), self.hooks['default_prompt'](), self.window())
        if dialog.exec():
            self.hooks['set_prompt'](dialog.text())
            self.refresh()


class PromptDialog(QDialog):
    """Edit the cleanup prompt. Ours stays one click away."""
    def __init__(self, current, default, parent=None):
        super().__init__(parent)
        self.default = default
        self.setWindowTitle('Cleanup prompt')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(640, 520)
        Headline('YOUR PROMPT', 64, parent=self).move(36, 30)
        label('The instructions auto cleanup follows. Write how you talk:\nwhat to drop, what to keep, how to punctuate.', body(13), G, self).move(36, 110)
        self.edit = QPlainTextEdit(self); self.edit.setGeometry(36, 162, 568, 230)
        self.edit.setFont(body(14)); self.edit.setPlainText(current)
        self.edit.setStyleSheet(f'QPlainTextEdit {{ background:#070707; border:1px solid {LINE}; border-radius:8px; padding:12px; color:{W}; }}'
                                f' QPlainTextEdit:focus {{ border-color:{G2}; }}')
        label('Safety net stays on: if a cleanup changes meaning (who, not, never) or adds or cuts too much,\nNuffSaid keeps your original words. So prompts that rewrite heavily get skipped.',
              body(11), G2, self).move(36, 402)
        reset = Pill('Reset to ours', self); reset.move(36, 462); reset.clicked.connect(lambda: self.edit.setPlainText(self.default))
        cancel = Pill('Cancel', self); cancel.move(448, 462); cancel.clicked.connect(self.reject)
        save = Pill('Save', self); save.move(530, 462); save.clicked.connect(self.accept)
        save.setStyleSheet(f"QPushButton {{ color:{K}; background:{W}; border:1px solid {W}; border-radius:13px; padding:0 16px; }} QPushButton:hover {{ background:#dcdcdc; }}")
        self._drag = None

    def text(self):
        return self.edit.toPlainText()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(.5, .5, self.width() - 1, self.height() - 1), 10, 10)
        p.fillPath(path, QColor(K)); p.setPen(QPen(QColor('#262626'), 1)); p.drawPath(path); p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 100:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None


class Sheet(QDialog):
    """Frameless black sheet in the window style; drag it by the top."""
    def __init__(self, w, h, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(w, h)
        self._drag = None

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(.5, .5, self.width() - 1, self.height() - 1), 10, 10)
        p.fillPath(path, QColor(K)); p.setPen(QPen(QColor('#262626'), 1)); p.drawPath(path); p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 100:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None


PROVIDERS = [('OpenRouter', 'https://openrouter.ai/api/v1', 'nvidia/nemotron-3.5-lightning:free'),
             ('OpenAI', 'https://api.openai.com/v1', ''),
             ('Groq', 'https://api.groq.com/openai/v1', ''),
             ('Other (OpenAI-compatible)', '', '')]


class EngineDialog(Sheet):
    """Choose where cleanup runs: on this PC (Ollama) or an online API with your own key."""
    def __init__(self, hooks, parent=None):
        super().__init__(640, 560, parent)
        from PyQt6.QtWidgets import QComboBox
        self.hooks, st = hooks, hooks['engine_state']()
        Headline('CLEANUP ENGINE', 60, parent=self).move(36, 30)
        seg = QWidget(self); sl = QHBoxLayout(seg); sl.setContentsMargins(0, 0, 0, 0); sl.setSpacing(0)
        seg.setGeometry(36, 110, 568, 40)
        self.local_btn, self.api_btn = QPushButton('On this PC'), QPushButton('Online API')
        for b, v in ((self.local_btn, 'ollama'), (self.api_btn, 'api')):
            b.setCursor(Qt.CursorShape.PointingHandCursor); b.clicked.connect(lambda _=False, v=v: self.set_mode(v)); sl.addWidget(b)

        self.local = QWidget(self); self.local.setGeometry(36, 170, 568, 260)
        ll = QVBoxLayout(self.local); ll.setContentsMargins(0, 0, 0, 0); ll.setSpacing(8)
        ll.addWidget(label('Ollama model', mono(10), G))
        self.models = QComboBox(); self.models.setFont(body(14)); ll.addWidget(self.models)
        try:
            names = hooks['ollama_models']() or []
        except Exception:
            names = []
        self.models.addItems(names or [st['ollama_model']])
        self.models.setCurrentText(st['ollama_model'])
        ll.addSpacing(10)
        ll.addWidget(label('Free and private: runs on your graphics card, nothing leaves your PC.\n'
                           'Needs Ollama (ollama.com) with a model pulled.' + ('' if names else '\nOllama is not running right now.'),
                           body(12), G, wrap=True))
        ll.addStretch(1)

        self.api = QWidget(self); self.api.setGeometry(36, 170, 568, 260)
        al = QGridLayout(self.api); al.setContentsMargins(0, 0, 0, 0); al.setHorizontalSpacing(16); al.setVerticalSpacing(6)
        al.addWidget(label('Provider', mono(10), G), 0, 0); al.addWidget(label('Model', mono(10), G), 0, 1)
        self.provider = QComboBox(); self.provider.setFont(body(14)); self.provider.addItems([p[0] for p in PROVIDERS])
        self.model = QLineEdit(st['model']); self.model.setPlaceholderText('model id from your provider')
        al.addWidget(self.provider, 1, 0); al.addWidget(self.model, 1, 1)
        al.addWidget(label('API address', mono(10), G), 2, 0, 1, 2)
        self.base = QLineEdit(st['base_url']); al.addWidget(self.base, 3, 0, 1, 2)
        al.addWidget(label('API key', mono(10), G), 4, 0, 1, 2)
        self.key = QLineEdit(); self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText('Saved on this PC, encrypted. Paste to replace.' if st['has_key'] else 'Paste your key')
        al.addWidget(self.key, 5, 0, 1, 2)
        al.addWidget(label('Your dictated text (never audio) goes to this provider. The key stays on this PC, encrypted for your Windows account.',
                           body(12), G, wrap=True), 6, 0, 1, 2)
        al.setRowStretch(7, 1)
        match = next((i for i, p in enumerate(PROVIDERS) if p[1] and p[1] in st['base_url']), len(PROVIDERS) - 1)
        self.provider.setCurrentIndex(match)
        self.provider.currentIndexChanged.connect(self.pick_provider)

        self.status = label('', body(12), G, self, wrap=True); self.status.setGeometry(36, 436, 568, 40)
        test = Pill('Test', self); test.move(36, 498); test.clicked.connect(self.test)
        cancel = Pill('Cancel', self); cancel.move(448, 498); cancel.clicked.connect(self.reject)
        save = Pill('Save', self); save.move(530, 498); save.clicked.connect(self.save)
        save.setStyleSheet(f"QPushButton {{ color:{K}; background:{W}; border:1px solid {W}; border-radius:13px; padding:0 16px; }} QPushButton:hover {{ background:#dcdcdc; }}")
        self.set_mode(st['backend'])

    def pick_provider(self, index):
        name, base, model = PROVIDERS[index]
        if base:
            self.base.setText(base)
        if model or not self.model.text():
            self.model.setText(model)

    def set_mode(self, mode):
        self.mode = mode
        self.local.setVisible(mode == 'ollama'); self.api.setVisible(mode == 'api')
        on = f'background:{W}; color:{K}; border:1px solid {W};'
        off = f'background:transparent; color:{G}; border:1px solid {G2};'
        self.local_btn.setStyleSheet(f'QPushButton {{ {on if mode == "ollama" else off} border-top-left-radius:6px; border-bottom-left-radius:6px; border-top-right-radius:0; border-bottom-right-radius:0; padding:10px; }}')
        self.api_btn.setStyleSheet(f'QPushButton {{ {on if mode == "api" else off} border-top-right-radius:6px; border-bottom-right-radius:6px; border-top-left-radius:0; border-bottom-left-radius:0; padding:10px; }}')

    def choice(self):
        if self.mode == 'ollama':
            return {'backend': 'ollama', 'ollama_model': self.models.currentText()}
        return {'backend': 'api', 'base_url': self.base.text().strip(), 'model': self.model.text().strip(), 'key': self.key.text().strip()}

    def test(self):
        c = self.choice()
        if c['backend'] == 'api' and (not c['base_url'] or not c['model']):
            self.status.setText('Fill in the API address and model.'); return
        self.status.setText('Testing with a sample sentence…'); QApplication.processEvents()
        ok, msg = self.hooks['test_engine'](c)
        self.status.setStyleSheet(f'color:{W if ok else G}; background:transparent;')
        self.status.setText(('Works. ' if ok else 'Did not work: ') + msg)

    def save(self):
        c = self.choice()
        if c['backend'] == 'api' and (not c['base_url'] or not c['model']):
            self.status.setText('Fill in the API address and model.'); return
        error = self.hooks['save_engine'](c)
        if error:
            self.status.setText(error)
        else:
            self.accept()


# --- Window ------------------------------------------------------------------------------------------------------
class MainWindow(QWidget):
    PAGES = [('home', 'Home', HomePage), ('history', 'History', HistoryPage), ('dictionary', 'Dictionary', DictionaryPage),
             ('blob', 'Blob', BlobPage), ('settings', 'Settings', SettingsPage)]

    def __init__(self, hooks):
        super().__init__()
        self.hooks = hooks
        self.setWindowTitle('NuffSaid')
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(962, 622)
        self._drag = None
        bar = QWidget(self); bar.setGeometry(1, 1, 960, 38)
        label('NuffSaid', mono(11), G, bar).move(18, 11)
        mini = Link('—', G, bar); mini.setFont(body(14)); mini.setGeometry(880, 6, 28, 26); mini.clicked.connect(self.showMinimized)
        close = Link('✕', G, bar); close.setFont(body(13)); close.setGeometry(918, 6, 28, 26); close.clicked.connect(self.close_to_tray)
        self.bar = bar
        rail = QWidget(self); rail.setGeometry(1, 39, 184, 582)
        r = QVBoxLayout(rail); r.setContentsMargins(0, 26, 0, 18); r.setSpacing(0)
        self.stack = QStackedWidget(self); self.stack.setGeometry(186, 39, 775, 582)
        self.buttons, self.pages = {}, {}
        for i, (key, title, cls) in enumerate(self.PAGES):
            b = QPushButton(f'0{i + 1}   {title}'); b.setFont(mono(12)); b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.open(k)); r.addWidget(b); self.buttons[key] = b
            page = cls(hooks); self.stack.addWidget(page); self.pages[key] = page
        r.addStretch(1)
        r.addWidget(label(f"v{hooks.get('version', '1.0')} · Windows\nClose me anytime.\nI live in your tray.", mono(9), G2))
        r.itemAt(r.count() - 1).widget().setContentsMargins(22, 0, 0, 0)
        self.current = None

    def open(self, key='home'):
        if self.current == 'blob' and key != 'blob':
            self.pages['blob'].leave()
        self.current = key
        for k, b in self.buttons.items():
            on = k == key
            b.setStyleSheet(f"QPushButton {{ text-align:left; border:none; border-left:2px solid {W if on else 'transparent'}; border-radius:0;"
                            f" padding:9px 20px; color:{W if on else G}; background:transparent; }} QPushButton:hover {{ color:{W}; }}")
        page = self.pages[key]
        page.refresh()
        self.stack.setCurrentWidget(page)
        self.showNormal(); self.raise_(); self.activateWindow()

    def set_update(self, version, url):
        """Show the new version on Home, one click to download the installer (it updates in place)."""
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        home = self.pages['home']
        home.update_btn.setText(f'NuffSaid {version} is out · Download')
        home.update_btn.adjustSize(); home.update_btn.move(44, 30)
        try:
            home.update_btn.clicked.disconnect()
        except TypeError:
            pass
        home.update_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        home.update_btn.show(); home.update_btn.raise_()
        home.status_label.hide()

    def close_to_tray(self):
        self.hide()
        if not getattr(self, '_told', False) and self.hooks.get('notice'):
            self._told = True
            self.hooks['notice']('Still running in your tray. Hold Ctrl+Win anytime.')

    def refresh_cleanup(self):
        self.pages['settings'].cleanup.set_on(self.hooks['cleanup_on']())

    def hideEvent(self, event):
        if self.current == 'blob':
            self.pages['blob'].leave()
        super().hideEvent(event)

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath(); path.addRoundedRect(QRectF(.5, .5, self.width() - 1, self.height() - 1), 10, 10)
        p.fillPath(path, QColor(K)); p.setPen(QPen(QColor('#262626'), 1)); p.drawPath(path)
        p.setPen(QColor(LINE)); p.drawLine(1, 39, self.width() - 2, 39); p.drawLine(185, 40, 185, self.height() - 2)
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and event.position().y() < 40:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None


# --- Tray menu ---------------------------------------------------------------------------------------------------
class _MenuBlock(QWidget):
    def paintEvent(self, event):
        p = QPainter(self); p.setPen(QColor(LINE)); p.drawLine(0, self.height() - 1, self.width(), self.height() - 1); p.end()


def build_tray_menu(open_home, open_history, open_dictionary, test_mic, toggle_cleanup, cleanup_on, quit_app):
    """Returns (menu, cleanup_toggle, status_label)."""
    menu = QMenu()
    menu.setMinimumWidth(300)
    menu.setFont(mono(11))

    head = _MenuBlock(); h = QHBoxLayout(head); h.setContentsMargins(20, 6, 20, 14)
    h.addWidget(Headline('NUFFSAID', 32)); h.addStretch(1)
    status = label('Ready', mono(9), G); h.addWidget(status)
    wa = QWidgetAction(menu); wa.setDefaultWidget(head); menu.addAction(wa)

    keys = _MenuBlock(); k = QGridLayout(keys); k.setContentsMargins(20, 12, 20, 12); k.setVerticalSpacing(5)
    for i, (a, b) in enumerate([('Dictate', 'Hold Ctrl+Win'), ('Hands-free', 'Double-tap Ctrl+Win'),
                                ('Clean up selection', 'Win+Alt+E'), ('Paste again', 'Win+Alt+S')]):
        k.addWidget(label(a, mono(10), G), i, 0); k.addWidget(label(b, mono(10)), i, 1, Qt.AlignmentFlag.AlignRight)
    wa = QWidgetAction(menu); wa.setDefaultWidget(keys); menu.addAction(wa)

    row = _MenuBlock(); r = QHBoxLayout(row); r.setContentsMargins(20, 12, 20, 12)
    text = QVBoxLayout(); text.setSpacing(3)
    text.addWidget(label('Auto cleanup', mono(11))); text.addWidget(label('Off = instant paste', mono(9), G))
    r.addLayout(text); r.addStretch(1)
    toggle = Toggle(cleanup_on()); toggle.toggled.connect(lambda v: toggle_cleanup()); r.addWidget(toggle)
    wa = QWidgetAction(menu); wa.setDefaultWidget(row); menu.addAction(wa)

    for title, fn in [('Open NuffSaid', open_home), ('History', open_history), ('Dictionary', open_dictionary),
                      ('Test microphone', test_mic)]:
        menu.addAction(title).triggered.connect(fn)
    menu.addSeparator()
    q = menu.addAction('Quit'); q.triggered.connect(quit_app)
    return menu, toggle, status
