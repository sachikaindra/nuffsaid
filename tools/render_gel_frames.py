"""Pre-render the real gel shader into sprite sheets for PCs without usable OpenGL (VMs, Windows Sandbox, remote desktops).
Run on a machine with a GPU:  python tools/render_gel_frames.py   ->  assets/gel-frames-{idle,speak,clean}.png
Each sheet is FRAMES frames of SIZE px in a 6x6 grid, phase 0..SPAN; the app plays them ping-pong so the loop never jumps."""
import sys
from pathlib import Path
from PyQt6.QtGui import QGuiApplication, QImage, QPainter
from PyQt6.QtCore import QRect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gel_renderer import GelRenderer

FRAMES, COLS, SIZE, SPAN = 36, 6, 256, 12.0
GLOW = .65 * 1.25
STATES = {  # (deformation, green, glow) matching FluidMotion's settled values per state
    'idle': (.087, 0., 0.),
    'speak': (.16, 0., GLOW),
    'clean': (.077, 1., .6 * GLOW),
}

app = QGuiApplication(sys.argv)
renderer = GelRenderer()
out = Path(__file__).resolve().parents[1] / 'assets'
for name, (deform, green, glow) in STATES.items():
    sheet = QImage(COLS * SIZE, (FRAMES // COLS) * SIZE, QImage.Format.Format_ARGB32)
    sheet.fill(0)
    p = QPainter(sheet)
    for i in range(FRAMES):
        frame = renderer.render(SIZE, SPAN * i / (FRAMES - 1), deform, green, 1 / 1.08, glow)
        p.drawImage(QRect((i % COLS) * SIZE, (i // COLS) * SIZE, SIZE, SIZE), frame)
    p.end()
    sheet.save(str(out / f'gel-frames-{name}.png'))
    print('saved', name)
renderer.close()
