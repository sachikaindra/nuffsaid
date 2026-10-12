"""Small, streaming speech-envelope rhythm estimate; does not store or transcribe audio."""
from collections import deque
from dataclasses import dataclass
import math
import time
import numpy as np


@dataclass(frozen=True)
class MotionSample:
    speaking: bool = False
    pace: float = 0.
    updated_at: float = 0.


class SpeechMotion:
    """Estimate syllabic rises, not words/minute, independently of overall gain.

    Analyze 20 ms frames even when the recorder supplies larger buffers. Relative
    envelope valleys/rises make quiet syllables as useful as loud ones. A noise
    floor gates silence; the renderer handles the gradual settling separately.
    """
    def __init__(self, sample_rate=16000, cutoff_db=-46):
        self.sample_rate = sample_rate
        self.cutoff = 10**(cutoff_db/20)
        self.frame_size = max(1, round(sample_rate * .02))
        self.reset()

    def reset(self):
        self.pending = np.empty(0, dtype=np.float32)
        self.elapsed = 0.
        self.noise = .00025
        self.envelope = 0.
        self.peak = 0.
        self.valley = 1.
        self.rising = False
        self.onsets = deque(maxlen=16)
        self.last_voice = -10.
        self.sample = MotionSample()

    def feed(self, samples):
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        self.pending = np.concatenate((self.pending, samples))
        count = len(self.pending) // self.frame_size
        for index in range(count):
            frame = self.pending[index*self.frame_size:(index+1)*self.frame_size]
            # Remove DC offset without changing the audio sent to transcription.
            rms = float(np.sqrt(np.mean((frame - frame.mean()) ** 2)))
            self._frame(rms)
        self.pending = self.pending[count*self.frame_size:]
        return self.sample

    def _frame(self, rms):
        dt = self.frame_size / self.sample_rate
        self.elapsed += dt
        if rms < self.noise * 2:
            self.noise += (rms-self.noise) * (1-math.exp(-dt/1.5))
        self.noise = max(.00008, min(.003, self.noise))
        threshold = max(self.cutoff, self.noise * 2.8)
        voiced = rms > threshold
        self.envelope += (rms-self.envelope) * (1-math.exp(-dt/.025))
        envelope = self.envelope
        if voiced:
            self.last_voice = self.elapsed
            self.valley = min(self.valley, envelope)
            self.peak = max(self.peak, envelope)
            if self.rising and envelope < self.peak * .77:
                self.rising = False
                self.valley = envelope
            rise = envelope > max(threshold, self.valley * 1.38)
            if not self.onsets or (not self.rising and rise and self.elapsed-self.onsets[-1] >= .12):
                self.onsets.append(self.elapsed)
                self.rising = True
                self.peak = envelope
        else:
            self.rising = False
            self.valley = min(self.valley, envelope)
            self.peak = envelope
        while self.onsets and self.elapsed-self.onsets[0] > 2.2:
            self.onsets.popleft()
        # Two or three envelope rises reveal pace; the first syllable responds
        # immediately at a moderate speed instead of waiting for a full window.
        pace = .25
        if len(self.onsets) >= 2:
            gaps = np.diff(tuple(self.onsets)[-6:])
            rate = 1. / max(.16, float(np.median(gaps)))
            pace = max(0., min(1., (rate-1.2)/4.8))
        speaking = self.elapsed-self.last_voice < .14
        self.sample = MotionSample(speaking, pace if speaking else 0., time.monotonic())


def entrance_scale(seconds):
    t = max(0., seconds)
    if t < .13:
        u = t/.13
        return -2*u**3+3*u*u+.2912*(u**3-u*u)
    if t >= .72:
        return 1.
    fade = min(1., max(0., (t-.48)/.24))
    envelope = 1-fade**3*(10+fade*(-15+6*fade))
    return 1+.08*math.exp(-7*(t-.13))*math.sin(28*(t-.13))*envelope


class FluidMotion:
    """Approved study motion, with live syllabic cadence between slow and fast."""
    def __init__(self):
        self.drive = self.energy = .31
        self.phase = 1.4
        self.activity = 0.
        self.motion_boost = 1.1
        self.speed_boost = 1.265

    @property
    def deformation(self):
        return min(.20, (.025+.175*self.energy)*self.motion_boost)

    def advance(self, dt, sample, polish=False, released=False):
        dt = max(0., min(.05, dt))
        pace = max(0., min(1., sample.pace)) if sample.speaking else 0.
        target = .26 if polish else .31+.61*pace
        speed = 2.13785 if polish or sample.speaking else 1.265
        # Interpolate actual phase velocity: fast speech must never slow down
        # while transitioning between the demonstration's two speed multipliers.
        velocity = 2.6680368+(2.956-2.6680368)*pace
        if sample.speaking and not polish:
            speed = velocity/(.38+2.8*target)
        active = .6 if polish else .75+.25*pace if sample.speaking else 0.
        if released:
            target, active = 0., 0.
        self.motion_boost += ((1.1-.1*pace)-self.motion_boost)*(1-math.exp(-dt*6))
        self.speed_boost += (speed-self.speed_boost)*(1-math.exp(-dt*6))
        self.drive += (target-self.drive)*(1-math.exp(-dt/(.07 if target>self.drive else .95)))
        self.energy += (self.drive-self.energy)*(1-math.exp(-dt/(.13 if self.drive>self.energy else .7)))
        self.phase += dt*(.38+2.8*self.energy)*self.speed_boost
        self.activity += (active-self.activity)*(1-math.exp(-dt/(.09 if active>self.activity else .55)))


def surface_radius(angle, phase, energy):
    """Broad, drifting lobes: bounded ±5% at rest, up to ±30% in speech."""
    field = (.54*math.sin(2*angle + phase*.87 + .3*math.sin(phase*.31))
             + .33*math.sin(3*angle - phase*.63 + .6)
             + .13*math.cos(4*angle + phase*.39))
    return 1. + min(.20, .025 + .175*energy)*field
