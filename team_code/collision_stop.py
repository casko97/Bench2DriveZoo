"""Track repeated CARLA collision callbacks on consecutive simulation frames."""
import threading


class SustainedCollisionStop:
    def __init__(self, threshold):
        self.threshold = threshold
        self.lock = threading.Lock()
        self.reset()

    def reset(self):
        with self.lock:
            self.actor_id = None
            self.frame = None
            self.count = 0
            self.pending = None

    def observe(self, actor_id, frame, accepted=False):
        with self.lock:
            if not self.threshold or self.pending is not None:
                return
            if self.actor_id == actor_id and self.frame == frame:
                return
            if self.actor_id == actor_id and self.frame is not None and frame == self.frame + 1:
                self.count += 1
            elif accepted:
                self.count = 1
            else:
                self.actor_id, self.frame, self.count = None, None, 0
                return
            self.actor_id, self.frame = actor_id, frame
            if self.count >= self.threshold:
                self.pending = {'actor_id': actor_id, 'frame': frame, 'consecutive_frames': self.count}

    def take_stop(self):
        with self.lock:
            pending, self.pending = self.pending, None
            return pending
