"""Append benchmark criterion events to a human-readable JSONL log."""
import json
import os
import threading
from datetime import datetime

_lock = threading.Lock()


def _encode(value):
    if hasattr(value, 'type_id') and hasattr(value, 'id'):
        return {'id': value.id, 'type_id': value.type_id}
    if all(hasattr(value, axis) for axis in ('x', 'y', 'z')):
        return {'x': value.x, 'y': value.y, 'z': value.z}
    return str(value)


def write_event(event, criterion, change):
    if event.get_type().name == 'ROUTE_COMPLETION':
        return
    record = {'time': datetime.now().astimezone().isoformat(),
              'criterion': criterion, 'change': change,
              'type': event.get_type().name, 'frame': event.get_frame(),
              'message': event.get_message(), 'details': event.get_dict()}
    try:
        with _lock:
            path = os.path.join(os.environ['SAVE_PATH'], 'live_events.jsonl')
            with open(path, 'a') as f:
                f.write(json.dumps(record, default=_encode) + '\n')
            print('[benchmark event] {}: {}'.format(record['type'], record['message']), flush=True)
    except (OSError, TypeError, ValueError) as exc:
        print('[benchmark event] Could not write live event: {}'.format(exc), flush=True)


def write_stop(details):
    record = {'time': datetime.now().astimezone().isoformat(),
              'type': 'SUSTAINED_COLLISION_STOP', 'details': details}
    try:
        with _lock:
            with open(os.path.join(os.environ['SAVE_PATH'], 'live_events.jsonl'), 'a') as f:
                f.write(json.dumps(record) + '\n')
    except OSError as exc:
        print('[benchmark event] Could not write stop reason: {}'.format(exc), flush=True)
    print('[route stop] Sustained collision: {}'.format(details), flush=True)


class EventList(list):
    def __init__(self, criterion):
        super().__init__()
        self.criterion = criterion

    def append(self, event):
        super().append(event)
        event._live_event_criterion = self.criterion
        write_event(event, self.criterion, 'created')
