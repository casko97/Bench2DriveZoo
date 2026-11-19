"""Bounded asynchronous event-window collection and persistence."""

from collections import deque
from dataclasses import dataclass, field
import queue
import threading
import uuid

from .contracts import Anchor, EventWindow, Frame, Trigger
from .store import FeedbackStore


@dataclass
class CapturedFrame:
    number: int
    time: float
    ego: dict
    actors: list
    lights: list
    context: dict
    sensors: dict  # name -> (frame number, array-like data)
    missing: list = field(default_factory=list)


@dataclass
class EncodedFrame:
    number: int
    time: float
    ego: dict
    actors: list
    lights: list
    context: dict
    sensors: dict  # name -> (sensor frame, PNG bytes)
    missing: list = field(default_factory=list)

    @property
    def size(self):
        return sum(len(value[1]) for value in self.sensors.values())


class WindowAssembler:
    """Match late triggers by frame number and emit complete or incomplete windows."""

    def __init__(self, before, after, max_bytes, max_pending, callback):
        if before < 0 or after < 0 or max_bytes <= 0 or max_pending <= 0:
            raise ValueError('Window durations must be non-negative and limits positive')
        self.before, self.after = before, after
        self.max_bytes, self.max_pending = max_bytes, max_pending
        self.callback = callback
        self.buffer = deque()
        self.buffer_bytes = 0
        self.pending = []

    def frame(self, frame):
        self.buffer.append(frame)
        self.buffer_bytes += frame.size
        # Keep extra time for post-trigger frames and late benchmark callbacks.
        while self.buffer and (self.buffer_bytes > self.max_bytes or
                frame.time - self.buffer[0].time > self.before + self.after + 2):
            self.buffer_bytes -= self.buffer.popleft().size
        self._advance()
        self._enforce_memory_limit()

    def trigger(self, event):
        if len(self.pending) >= self.max_pending:
            self._finish(self.pending.pop(0), 'pending event limit reached')
        self.pending.append({'event': event, 'frames': {}, 'anchor_time': None})
        self._advance()
        self._enforce_memory_limit()

    def _enforce_memory_limit(self):
        # Windows can retain frames that have left the rolling buffer. Count
        # distinct frame objects once, and truncate the oldest pending event
        # if those retained frames would exceed the configured memory budget.
        while self.pending:
            unique = {id(frame): frame for frame in self.buffer}
            for item in self.pending:
                unique.update({id(frame): frame for frame in item['frames'].values()})
            if sum(frame.size for frame in unique.values()) <= self.max_bytes:
                break
            self._finish(self.pending.pop(0), 'window buffer memory limit reached')

    def _advance(self):
        if not self.buffer:
            return
        for item in list(self.pending):
            if item['anchor_time'] is None:
                anchor = next((frame for frame in self.buffer if frame.number == item['event']['frame']), None)
                if anchor is not None:
                    item['anchor_time'] = anchor.time
            if item['anchor_time'] is not None:
                start = item['anchor_time'] - self.before
                end = item['anchor_time'] + self.after
                for frame in self.buffer:
                    if start - 1e-6 <= frame.time <= end + 1e-6:
                        item['frames'][frame.number] = frame
                if self.buffer[-1].time >= end - 1e-6:
                    self.pending.remove(item)
                    self._finish(item, None)

    def finish(self):
        for item in self.pending:
            self._finish(item, 'route ended before window was complete')
        self.pending.clear()

    def _finish(self, item, reason):
        frames = sorted(item['frames'].values(), key=lambda frame: frame.number)
        anchor = item['anchor_time']
        if anchor is None:
            reason = reason or 'trigger frame was not captured'
        if anchor is not None:
            actual_before = anchor - frames[0].time if frames else 0.0
            actual_after = frames[-1].time - anchor if frames else 0.0
            if actual_before + 1e-6 < self.before or actual_after + 1e-6 < self.after:
                reason = reason or 'insufficient window coverage'
            if any(b.number != a.number + 1 for a, b in zip(frames, frames[1:])):
                reason = reason or 'missing simulation frames'
            if any(frame.missing for frame in frames):
                reason = reason or 'missing or unsynchronized sensor data'
        else:
            actual_before = actual_after = 0.0
        self.callback(item['event'], frames, anchor, max(0.0, actual_before),
                      max(0.0, actual_after), reason)


class AsyncWindowRecorder:
    """One writer thread owns SQLite and image encoding; frames may be dropped under load."""

    def __init__(self, root, round_data, run_data, before=1.0, after=1.0,
                 max_bytes=256 * 1024 * 1024, queue_size=2, max_pending=4):
        if queue_size <= 0:
            raise ValueError('queue_size must be positive')
        self.root, self.round_data, self.run_data = root, round_data, run_data
        self.before, self.after = before, after
        self.queue = queue.Queue(maxsize=queue_size)
        self.dropped_frames = 0
        self.error = None
        self._closed = False
        self.assembler = WindowAssembler(before, after, max_bytes, max_pending, self._persist)
        self.thread = threading.Thread(target=self._run, name='feedback-window-writer', daemon=True)
        self.thread.start()

    def frame(self, frame):
        if self._closed or self.error:
            raise RuntimeError('Window recorder is closed or failed')
        try:
            self.queue.put_nowait(('frame', frame))
        except queue.Full:
            self.dropped_frames += 1
            return False
        return True

    def trigger(self, event):
        if self._closed or self.error:
            raise RuntimeError('Window recorder is closed or failed')
        # Events are rare and must not be silently lost; wait for a writer slot.
        while not self.error:
            try:
                self.queue.put(('trigger', dict(event)), timeout=0.2)
                return
            except queue.Full:
                pass
        raise RuntimeError('Window recorder failed') from self.error

    def close(self):
        if self._closed:
            return
        self._closed = True
        while self.thread.is_alive():
            try:
                self.queue.put(('close', None), timeout=0.2)
                break
            except queue.Full:
                pass
        self.thread.join()
        if self.error:
            raise RuntimeError('Window recorder failed') from self.error

    def _run(self):
        try:
            with FeedbackStore(self.root) as self.store:
                try:
                    existing_round = self.store.get(self.round_data.id, verify_artifacts=False)
                except KeyError:
                    self.store.save(self.round_data)
                else:
                    if (existing_round.kind != 'training_round' or
                            existing_round.policy_checkpoint != self.round_data.policy_checkpoint or
                            existing_round.configuration != self.round_data.configuration):
                        raise ValueError('Round ID already exists with different checkpoint or configuration')
                self.store.save(self.run_data)
                while True:
                    kind, payload = self.queue.get()
                    if kind == 'close':
                        self.assembler.finish()
                        break
                    if kind == 'trigger':
                        self.assembler.trigger(payload)
                    else:
                        self.assembler.frame(self._encode(payload))
        except Exception as exc:
            self.error = exc

    @staticmethod
    def _encode(frame):
        import cv2
        sensors = {}
        missing = list(frame.missing)
        for name, (sensor_frame, image) in frame.sensors.items():
            success, encoded = cv2.imencode('.png', image)
            if not success:
                missing.append(name + ': encoding failed')
                continue
            sensors[name] = (sensor_frame, encoded.tobytes())
        return EncodedFrame(frame.number, frame.time, frame.ego, frame.actors,
                            frame.lights, frame.context, sensors, missing)

    def _persist(self, event, frames, anchor_time, actual_before, actual_after, reason):
        event_id = uuid.uuid4().hex
        run_id = self.run_data.id
        records = []
        for frame in frames:
            artifacts = {name: self.store.put_artifact(data, 'image/png')
                         for name, (_, data) in frame.sensors.items()}
            records.append(Frame('{}:{}'.format(run_id, frame.number), run_id=run_id,
                frame_number=frame.number, simulation_time_seconds=frame.time,
                coordinate_frames={'ego_state': 'CARLA world', 'actor_states': 'CARLA world'},
                ego_state=frame.ego, actor_states=frame.actors, traffic_lights=frame.lights,
                policy_context=frame.context, artifacts=artifacts,
                metadata={'sensor_frames': {name: number for name, (number, _) in frame.sensors.items()},
                          'missing': frame.missing}))
        trigger_frame_id = '{}:{}'.format(run_id, event['frame'])
        if not any(frame.number == event['frame'] for frame in frames):
            records.append(Frame(trigger_frame_id, run_id=run_id, frame_number=event['frame'],
                simulation_time_seconds=event['simulation_time_seconds'], status='failed',
                reason='trigger frame not captured', metadata={'placeholder': True}))
        trigger = Trigger(event_id, run_id=run_id, frame_id=trigger_frame_id,
                          trigger_type=event['type'], evidence=event['evidence'],
                          metadata={'processing_time_seconds': event['simulation_time_seconds']})
        window = EventWindow(uuid.uuid4().hex, trigger_id=event_id,
            frame_ids=[record.id for record in records if not record.metadata.get('placeholder')],
            requested_before_seconds=self.before, requested_after_seconds=self.after,
            actual_before_seconds=actual_before, actual_after_seconds=actual_after,
            status='complete' if reason is None else 'failed', reason=reason,
            metadata={'trigger_frame_time_seconds': anchor_time, 'dropped_frames': self.dropped_frames})
        anchors = []
        if anchor_time is not None and self.before > 0:
            target = anchor_time - self.before / 2
            candidates = [frame for frame in frames if frame.time < anchor_time]
            if candidates:
                selected = min(candidates, key=lambda frame: (abs(frame.time - target), frame.number))
                history = ['{}:{}'.format(run_id, frame.number) for frame in frames if frame.number < selected.number]
                anchors.append(Anchor(uuid.uuid4().hex, trigger_id=event_id,
                    frame_id='{}:{}'.format(run_id, selected.number), observation_history=history,
                    metadata={'selection': 'captured pre-trigger frame closest to window midpoint',
                              'temporal_bev_captured': False, 'replay_verified': False}))
        self.store.save(*(records + [trigger, window] + anchors))
