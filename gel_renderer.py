"""Approved gel shader, rendered offscreen for a transparent Windows overlay."""
import ctypes
import os
from pathlib import Path
import struct
from PyQt6.QtCore import QSize
from PyQt6.QtGui import QOpenGLContext, QOffscreenSurface, QSurfaceFormat, QImage
from PyQt6.QtOpenGL import QOpenGLShader, QOpenGLShaderProgram, QOpenGLBuffer, QOpenGLFramebufferObject


class GelRenderer:
    def __init__(self):
        fmt = QSurfaceFormat()
        fmt.setVersion(2, 1)
        fmt.setAlphaBufferSize(8)
        self.context = QOpenGLContext()
        self.context.setFormat(fmt)
        if not self.context.create():
            raise RuntimeError('OpenGL context unavailable')
        self.surface = QOffscreenSurface()
        self.surface.setFormat(self.context.format())
        self.surface.create()
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError('OpenGL surface unavailable')
        self.program = QOpenGLShaderProgram()
        vertex = '#version 120\nattribute vec2 position; varying vec2 uv; void main(){uv=position;gl_Position=vec4(position,0.,1.);}'
        fragment = Path(__file__).with_name('gel.frag').read_text()
        for kind, source in ((QOpenGLShader.ShaderTypeBit.Vertex, vertex), (QOpenGLShader.ShaderTypeBit.Fragment, fragment)):
            if not self.program.addShaderFromSourceCode(kind, source):
                raise RuntimeError(self.program.log())
        if not self.program.link():
            raise RuntimeError(self.program.log())
        self.buffer = QOpenGLBuffer()
        self.buffer.create()
        self.buffer.bind()
        vertices = struct.pack('12f', -1,-1,1,-1,-1,1,-1,1,1,-1,1,1)
        self.buffer.allocate(vertices, len(vertices))
        self.buffer.release()
        self.fbo = None
        self.gl = ctypes.WinDLL('opengl32')
        self.gl.glClearColor.argtypes = [ctypes.c_float]*4
        self.context.doneCurrent()

    def render(self, pixels, phase, deform, green, scale, glow):
        if os.environ.get('NUFFSAID_NO_GL'):   # for testing the fallbacks
            raise RuntimeError('OpenGL disabled by NUFFSAID_NO_GL')
        if not self.context.makeCurrent(self.surface):
            raise RuntimeError('Lost gel graphics context')
        try:
            if self.fbo is None or self.fbo.width() != pixels:
                self.fbo = QOpenGLFramebufferObject(QSize(pixels, pixels))
            if not self.fbo.isValid() or not self.fbo.bind():
                raise RuntimeError('Gel framebuffer unavailable')
            self.gl.glViewport(0, 0, pixels, pixels)
            self.gl.glClearColor(0, 0, 0, 0)
            self.gl.glClear(0x4000)
            self.program.bind()
            self.buffer.bind()
            loc = self.program.attributeLocation('position')
            self.program.enableAttributeArray(loc)
            self.program.setAttributeBuffer(loc, 0x1406, 0, 2)
            for key, value in dict(uPhase=phase,uDeform=deform,uGreen=green,uScale=scale,uGlow=glow,uViolet=32/60,uDepth=.75,uGloss=.85).items():
                self.program.setUniformValue(key, float(value))
            self.gl.glDrawArrays(0x0004, 0, 6)
            self.program.disableAttributeArray(loc)
            self.buffer.release()
            self.program.release()
            image = self.fbo.toImage()
            # Qt labels FBO readback as premultiplied; this shader emits straight
            # alpha, exactly like the approved WebGL canvas. Relabel, don't convert.
            image.reinterpretAsFormat(QImage.Format.Format_ARGB32)
            # No real OpenGL (Windows Sandbox, some VMs/remote desktops) renders silently empty. The blob's
            # centre is never transparent when scale > 0, so treat that as a failure and let the caller fall back.
            if scale > .05 and image.pixelColor(pixels // 2, pixels // 2).alpha() == 0:
                raise RuntimeError('Gel rendered empty (no usable OpenGL)')
            return image
        finally:
            if self.fbo:
                self.fbo.release()
            self.context.doneCurrent()

    def close(self):
        if self.context.makeCurrent(self.surface):
            self.fbo = None
            self.buffer.destroy()
            self.program.removeAllShaders()
            self.context.doneCurrent()
        self.surface.destroy()
