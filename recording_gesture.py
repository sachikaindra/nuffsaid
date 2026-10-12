"""Hold and double-tap recording gestures, independent of keyboard and Qt."""


class RecordingGesture:
    tap_seconds = 0.25
    double_seconds = 0.35
    release_seconds = 0.15

    def __init__(self):
        self.reset()

    def reset(self):
        self.active = False
        self.locked = False
        self.down = False
        self.pressed_at = 0.0
        self.deadline = None
        self.short_tap = False

    def press(self, now):
        if self.down:
            return None
        self.down = True
        if self.locked:
            self.reset()
            return 'stop'
        if self.active:
            if self.deadline is not None and now < self.deadline and self.short_tap:
                self.locked = True
                self.deadline = None
                return 'lock'
            self.deadline = None
            self.pressed_at = now
            return None
        self.active = True
        self.pressed_at = now
        return 'start'

    def release(self, now):
        if not self.down:
            return None
        self.down = False
        if not self.active or self.locked:
            return None
        self.short_tap = now - self.pressed_at <= self.tap_seconds
        delay = self.double_seconds if self.short_tap else self.release_seconds
        self.deadline = now + delay
        return delay

    def expire(self, now):
        if self.deadline is not None and now >= self.deadline:
            self.reset()
            return True
        return False
