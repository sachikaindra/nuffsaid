"""Focus-safe voice overlay and local appearance settings; no audio capture."""
import json
import logging
import math
import time
from pathlib import Path
GLOW = .65 * 1.25   # speech halo strength, +25% (owner, 2026-10-12); shared with ui_shell
BLOOM = ((0, 45), (.45, 28), (.75, 10), (1, 0))   # soft red bloom stops (alpha at full speech): 30% of the first version (owner, 2026-10-12)


def paint_bloom(painter, cx, cy, d, strength, green=0., limit=None):
    """Soft red bloom behind the gel, everywhere the gel appears. Follows the speech glow (strength 0..1)."""
    if strength <= .01:
        return
    from PyQt6.QtGui import QRadialGradient
    r = d * 1.05 if limit is None else min(d * 1.05, limit)
    grad = QRadialGradient(cx, cy, r)
    k = max(0., min(1., strength)) * (1 - .75 * green)
    for at, alpha in BLOOM:
        grad.setColorAt(at, QColor(255, 52, 30, int(alpha * k)))
    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(grad)
    painter.drawEllipse(QRectF(cx - r, cy - r, 2 * r, 2 * r))
from speech_motion import MotionSample, FluidMotion, surface_radius, entrance_scale
from gel_renderer import GelRenderer
from PyQt6.QtCore import Qt, QTimer, QPoint, QRectF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QLinearGradient, QRadialGradient, QPen, QCursor
from PyQt6.QtWidgets import QApplication, QWidget, QDialog, QVBoxLayout, QLabel, QSlider, QPushButton, QCheckBox


BAR_GLOW = 28   # px of glow above the bar at full speech


def paint_bar(p, width, bottom, phase, activity, polish=False):
    """The bottom bar (4 px) plus a soft glow rising from it while you speak. Used by the overlay and the dashboard preview."""
    color = QColor('#cfd4da' if polish else '#ff3a24')
    r, g, b = color.red(), color.green(), color.blue()
    center = .5 + .34*math.sin(phase*.45)
    k = max(0., min(1., activity)) * (.4 if polish else 1.)
    if k > .01:
        rise = QLinearGradient(0, bottom, 0, bottom - BAR_GLOW)
        rise.setColorAt(0, QColor(r, g, b, int(70*k))); rise.setColorAt(1, QColor(r, g, b, 0))
        p.fillRect(QRectF(0, bottom - BAR_GLOW, width, BAR_GLOW), rise)
        hot = QRadialGradient(width*center, bottom, width*.18)
        hot.setColorAt(0, QColor(r, g, b, int(90*k))); hot.setColorAt(1, QColor(r, g, b, 0))
        p.save(); p.translate(width*center, bottom); p.scale(1, BAR_GLOW/(width*.18)); p.translate(-width*center, -bottom)
        p.fillRect(QRectF(0, bottom - width*.18, width, width*.18), hot); p.restore()
    strip = QRectF(0, bottom - 4, width, 4)
    p.fillRect(strip, QColor(r, g, b, 115))
    gradient = QLinearGradient(0, 0, width, 0)
    gradient.setColorAt(0, QColor(r, g, b, 65))
    gradient.setColorAt(center, QColor(r, g, b, 235))
    gradient.setColorAt(1, QColor(r, g, b, 65))
    p.fillRect(strip, gradient)


class BottomBar(QWidget):
    """The unobtrusive fallback when the user hides the blob."""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus |
                            Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.mode = 'idle'
        self.app_mode = 'idle'
        self.energy = 0.
        self.phase = 0.
        self.activity = 0.

    def place(self, screen):
        g = screen.availableGeometry()
        self.setGeometry(g.left(), g.bottom()-3-BAR_GLOW, g.width(), 4+BAR_GLOW)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_bar(p, self.width(), self.height(), self.phase, self.activity, self.mode == 'polish')
        p.end()


class LiquidOverlay(QWidget):
    def __init__(self, get_audio_level_fn=None, settings_path=None):
        super().__init__()
        self.level_fn = get_audio_level_fn or (lambda: 0)
        self.path = Path(settings_path) if settings_path else None
        self.settings = dict(size=38, enabled=True, screen=None, x=.5, y=1.)
        try:
            data = json.loads(self.path.read_text()) if self.path else {}
            self.settings.update({k: data[k] for k in self.settings if k in data})
            self.settings['size'] = max(24, min(120, int(self.settings['size'])))
            for key in ('x', 'y'):
                self.settings[key] = max(0., min(1., float(self.settings[key])))
        except (OSError, ValueError, TypeError):
            logging.warning('Using default overlay settings')
            self.settings = dict(size=38, enabled=True, screen=None, x=.5, y=1.)
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus |
                            Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        # Space for the gel, halo, and small entrance overshoot at maximum size.
        self.setFixedSize(224, 224)
        self.bar = BottomBar()
        self.motion = FluidMotion()
        self.renderer = None
        self.renderer_failed = False
        self.mode = 'idle'
        self.app_mode = 'idle'
        self.editing = False
        self.energy = 0.
        self.phase = 0.
        self.green = 0.
        self.scale = 0.
        self.transition = None
        self.drag_offset = None
        self.dialog = None
        self.last_tick = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.place()
        QApplication.instance().screenRemoved.connect(lambda _: self.place())

    def save(self):
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix('.tmp')
            temp.write_text(json.dumps(self.settings, indent=2), encoding='utf-8')
            temp.replace(self.path)
        except OSError:
            logging.exception('Could not save overlay preferences')

    def place(self):
        screen = next((s for s in QApplication.screens() if s.name() == self.settings['screen']), QApplication.primaryScreen())
        if not screen:
            return
        g = screen.availableGeometry()
        margin = self.settings['size'] * .75 + 5
        cx = g.left() + margin + self.settings['x'] * max(0, g.width() - margin * 2)
        cy = g.top() + margin + self.settings['y'] * max(0, g.height() - margin * 2)
        self.move(round(cx - 112), round(cy - 112))
        self.bar.place(screen)

    def remember_position(self):
        center = self.pos() + QPoint(112, 112)
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        g = screen.availableGeometry()
        margin = self.settings['size'] * .75 + 5
        self.settings.update(screen=screen.name(),
                             x=max(0., min(1., (center.x()-g.left()-margin)/max(1., g.width()-2*margin))),
                             y=max(0., min(1., (center.y()-g.top()-margin)/max(1., g.height()-2*margin))))
        self.place()
        self.save()

    def show_mode(self, mode):
        old = self.mode
        self.mode = mode
        if not self.settings['enabled'] and not self.editing:
            self.hide()
            self.bar.mode = mode
            self.bar.setVisible(mode in ('recording', 'polish', 'transcribing'))
            if self.bar.isVisible():
                self.last_tick = time.monotonic()
                self.timer.start()
            else:
                self.timer.stop()
            return
        self.bar.hide()
        if mode in ('recording', 'polish') or self.editing:
            if not self.isVisible() or old not in ('recording', 'polish'):
                self.green = 1. if mode == 'polish' else 0.
                self.transition = ('in', time.monotonic(), 0.)
                self.scale = 0.
                self.energy = .31
                self.motion.drive = self.motion.energy = .31
            self.show()
            self.last_tick = time.monotonic()
            self.timer.start()
        elif self.isVisible() and (not self.transition or self.transition[0] != 'out'):
            self.transition = ('out', time.monotonic(), self.scale)
            self.timer.start()

    def set_app_state(self, state, message=''):
        value = getattr(state, 'value', state)
        self.app_mode = ('recording' if value == 'recording' else
                         'polish' if value == 'processing' and message == 'polish' else
                         'transcribing' if value == 'processing' else 'idle')
        self.show_mode(self.app_mode)

    def tick(self):
        now = time.monotonic()
        dt = min(.05, now-self.last_tick)
        self.last_tick = now
        if self.transition and not self.bar.isVisible():
            kind, start, initial = self.transition
            u = min(1., (now-start)/(.72 if kind == 'in' else .48))
            if kind == 'in':
                self.scale = entrance_scale(now-start)
            else:
                self.scale = initial*(1-u*u)
            if u >= 1:
                self.transition = None
                if kind == 'out':
                    self.hide()
                    self.green = 0.
                    self.timer.stop()
                    return
        sample = MotionSample()
        if self.mode == 'recording':
            try:
                sample = self.level_fn()
                if not isinstance(sample, MotionSample) or now-sample.updated_at > .35:
                    sample = MotionSample()
            except Exception:
                sample = MotionSample()
                logging.debug('Overlay speech rhythm unavailable', exc_info=True)
        self.motion.advance(dt, sample, polish=self.mode == 'polish',
                            released=bool(self.transition and self.transition[0] == 'out'))
        self.energy, self.phase = self.motion.energy, self.motion.phase
        # Preserve the exact visible tint until the exit has fully finished.
        if not (self.transition and self.transition[0] == 'out'):
            self.green += ((1. if self.mode == 'polish' else 0.)-self.green)*(1-math.exp(-dt*5))
        if self.bar.isVisible():
            self.bar.energy, self.bar.phase, self.bar.activity = self.energy, self.phase, self.motion.activity
            self.bar.update()
        else:
            self.update()

    def paintEvent(self, event):
        if not self.renderer_failed:
            try:
                if self.renderer is None:
                    self.renderer = GelRenderer()
                # Supersample the tiny surface before Windows composites it.
                extent = self.settings['size']*1.6*1.08
                pixels = max(192, min(512, round(extent*self.devicePixelRatioF()*2)))
                frame = self.renderer.render(pixels, self.phase, self.motion.deformation,
                                             self.green, self.scale/1.08, self.motion.activity*GLOW)
                painter = QPainter(self)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                paint_bloom(painter, 112, 112, self.settings['size']*self.scale, self.motion.activity, self.green, limit=110)
                painter.drawImage(QRectF(112-extent/2,112-extent/2,extent,extent), frame)
                if self.editing:
                    painter.setPen(QPen(QColor(160,170,195,180),1,Qt.PenStyle.DashLine))
                    painter.drawRoundedRect(QRectF(12,12,200,200),12,12)
                painter.end()
                return
            except Exception:
                logging.exception('Gel graphics unavailable; using the lightweight overlay')
                self.renderer_failed = True
        self.paint_fallback()

    def paint_fallback(self):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.editing:
            p.setPen(QPen(QColor(160, 170, 195, 180), 1, Qt.PenStyle.DashLine))
            p.drawRoundedRect(QRectF(12, 12, 200, 200), 12, 12)
        p.translate(112, 112)
        p.scale(max(.0001, self.scale), max(.0001, self.scale))
        radius = self.settings['size']/2
        p.scale(radius/130, radius/130)
        phase, e = self.phase, self.energy
        path = QPainterPath()
        for i in range(181):
            a = i/180*math.tau
            r = 130*surface_radius(a, phase, e)
            x,y = math.cos(a)*r, math.sin(a)*r
            path.moveTo(x,y) if i == 0 else path.lineTo(x,y)
        path.closeSubpath()
        # Red while listening, colourless glass during cleanup (2026-10-11).
        hue = 356/360
        def tint(light, alpha, saturation=.85):
            return QColor.fromHslF(hue, saturation*(1-self.green), light, alpha*(1-.6*self.green))
        base = QLinearGradient(-95,-135,103,135)
        for stop,color in [(0,QColor(248,252,255,190)),(.13,tint(.63,.6)),(.3,tint(.25,.28)),(.48,tint(.85,.07)),(.64,tint(.62,.14)),(.85,tint(.37,.54)),(1,tint(.78,.72))]:
            base.setColorAt(stop,color)
        p.fillPath(path,base)
        p.save()
        p.setClipPath(path)
        light=QRadialGradient(-57+math.sin(phase*.52)*28,-95+math.cos(phase*.43)*16,150)
        light.setColorAt(0,QColor(255,255,255,250));light.setColorAt(.12,QColor(238,246,255,130));light.setColorAt(1,QColor(255,255,255,0))
        p.fillRect(QRectF(-180,-180,360,360),light)
        bottom=QRadialGradient(36+math.sin(phase*.37)*25,112,128)
        bottom.setColorAt(0,tint(.76,.9));bottom.setColorAt(.35,tint(.60,.34));bottom.setColorAt(1,tint(.45,0))
        p.fillRect(QRectF(-180,-180,360,360),bottom)
        warm=QRadialGradient(103+math.sin(phase)*8,55,99)
        for stop,alpha in [(0,.8),(.25,.45),(.65,.12),(1,0)]:
            warm.setColorAt(stop,QColor.fromHslF(28/360,.95,.65,alpha*(1-self.green)))
        p.fillRect(QRectF(-180,-180,360,360),warm)
        # Broad travelling reflections convey a turning gel surface even with
        # only 5% silhouette deformation. No periodic whole-blob size pulse.
        sweep = math.sin(phase*.48)
        fold = QPainterPath()
        fold.moveTo(-138, -35+22*sweep)
        fold.cubicTo(-48, -120-15*sweep, 35, 68+30*sweep, 137, -30)
        fold.cubicTo(62, 8+20*sweep, -35, -71+15*sweep, -138, -35+22*sweep)
        reflection = QLinearGradient(-90,-95,85,60)
        reflection.setColorAt(0,QColor(228,243,255,10))
        reflection.setColorAt(.45,QColor(226,244,255,92))
        reflection.setColorAt(.7,tint(.67,.09))
        reflection.setColorAt(1,QColor(255,255,255,0))
        p.fillPath(fold, reflection)
        p.restore()
        edge=QLinearGradient(-92,-118,58,132)
        for stop,color in [(0,QColor(255,255,255,252)),(.2,tint(.88,.7)),(.45,QColor(40,50,65,66)),(.62,QColor(255,255,255,204)),(.75,tint(.66,.25)),(1,tint(.91,.95))]:
            edge.setColorAt(stop,color)
        p.setPen(QPen(edge,3));p.setBrush(Qt.BrushStyle.NoBrush);p.drawPath(path)
        p.end()

    def edit(self, enabled):
        self.editing = enabled
        self.bar.hide()
        self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, not enabled)
        self.setCursor(Qt.CursorShape.SizeAllCursor if enabled else Qt.CursorShape.ArrowCursor)
        if enabled:
            self.show_mode('preview')
        else:
            self.hide();self.timer.stop();self.mode='idle';self.scale=0.
            self.show_mode(self.app_mode)

    def mousePressEvent(self, event):
        if self.editing and event.button() == Qt.MouseButton.LeftButton:
            self.drag_offset = event.globalPosition().toPoint()-self.pos()

    def mouseMoveEvent(self, event):
        if self.editing and self.drag_offset is not None:
            self.move(event.globalPosition().toPoint()-self.drag_offset)

    def mouseReleaseEvent(self, event):
        if self.drag_offset is not None:
            self.drag_offset=None;self.remember_position()

    def open_settings(self):
        if self.dialog is None:
            self.dialog=QDialog()
            self.dialog.setWindowTitle('NuffSaid — Blob appearance')
            layout=QVBoxLayout(self.dialog)
            layout.addWidget(QLabel('Drag the blob to any screen position.\nClose this window when you are done.'))
            enabled=QCheckBox('Show liquid blob (off uses the bottom bar)')
            enabled.setChecked(bool(self.settings['enabled']))
            enabled.toggled.connect(lambda v: self.change('enabled',v))
            layout.addWidget(enabled)
            label=QLabel(f"Size: {self.settings['size']} px")
            layout.addWidget(label)
            slider=QSlider(Qt.Orientation.Horizontal)
            slider.setRange(24,120);slider.setValue(self.settings['size'])
            def resize(value):
                label.setText(f'Size: {value} px');self.change('size',value);self.place();self.update()
            slider.valueChanged.connect(resize);layout.addWidget(slider)
            reset=QPushButton('Reset position to bottom centre')
            def reset_position():
                self.settings.update(screen=QApplication.primaryScreen().name(),x=.5,y=1.);self.place();self.save()
            reset.clicked.connect(reset_position);layout.addWidget(reset)
            done=QPushButton('Done');done.clicked.connect(self.dialog.accept);layout.addWidget(done)
            self.dialog.finished.connect(lambda _: self.edit(False))
        self.edit(True)
        self.dialog.showNormal();self.dialog.raise_();self.dialog.activateWindow()

    def change(self,key,value):
        self.settings[key]=value;self.save()

    def closeEvent(self, event):
        self.timer.stop()
        self.bar.close()
        if self.renderer is not None:
            self.renderer.close()
            self.renderer = None
        if self.dialog:
            self.dialog.close()
        super().closeEvent(event)
