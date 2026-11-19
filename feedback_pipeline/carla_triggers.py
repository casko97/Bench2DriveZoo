"""Optional CARLA adapter for the evaluator; no simulator control is changed."""

import json
import os
from pathlib import Path
import threading

from .triggers import TriggerMonitor, TriggerPolicy


class CarlaTriggerAdapter:
    def __init__(self, path, cooldown=2.0, collision_policy=None, route_lanes_policy=None):
        self.path = path
        self.monitor = TriggerMonitor(cooldown, collision_policy, route_lanes_policy)
        self.route = None
        self.lock = threading.RLock()

    def reset(self, route):
        with self.lock:
            self.route = route
            self.monitor.reset()

    def _write(self, event):
        if event is not None:
            event['route'] = self.route
            with open(self.path, 'a', encoding='utf-8') as handle:
                handle.write(json.dumps(event, allow_nan=False, sort_keys=True) + '\n')
            print('[feedback trigger] {} frame={}'.format(event['type'], event['frame']), flush=True)

    def benchmark_event(self, event, change, frame, simulation_time):
        event_type = event.get_type().name
        with self.lock:
            if event_type in ('COLLISION_STATIC', 'COLLISION_VEHICLE', 'COLLISION_PEDESTRIAN') and change == 'created':
                actor = event.get_dict()['other_actor']
                self._write(self.monitor.collision(frame, simulation_time, actor.id,
                            {'actor_id': str(actor.id), 'actor_type': actor.type_id,
                             'source': event_type, 'message': event.get_message()}))
            elif event_type == 'OUTSIDE_ROUTE_LANES_INFRACTION' and change == 'updated':
                self._write(self.monitor.route_lanes_infraction(frame, simulation_time,
                            {'source': event_type, 'details': dict(event.get_dict()),
                             'message': event.get_message()}))

def load_trigger_config(path):
    """Read and validate both reason policies, rejecting typos and invalid values."""
    with open(path, 'r', encoding='utf-8') as handle:
        config = json.load(handle)
    reasons = {'collision', 'outside_route_lanes_infraction'}
    if not isinstance(config, dict) or set(config) != reasons:
        raise ValueError('Trigger config must contain exactly: {}'.format(', '.join(sorted(reasons))))
    policies = {}
    for reason, values in config.items():
        if not isinstance(values, dict) or set(values) != {'mode', 'cooldown_seconds'}:
            raise ValueError('{} must contain mode and cooldown_seconds'.format(reason))
        cooldown = values['cooldown_seconds']
        if isinstance(cooldown, bool) or not isinstance(cooldown, (int, float)):
            raise ValueError('{} cooldown_seconds must be a number'.format(reason))
        policies[reason] = TriggerPolicy(values['mode'], cooldown)
    return policies


def adapter_from_environment():
    if os.environ.get('FEEDBACK_TRIGGERS', '0') != '1':
        return None
    default_path = Path(__file__).with_name('trigger_config.json')
    policies = load_trigger_config(os.environ.get('FEEDBACK_TRIGGER_CONFIG', str(default_path)))
    return CarlaTriggerAdapter(os.path.join(os.environ['SAVE_PATH'], 'feedback_triggers.jsonl'),
                               collision_policy=policies['collision'],
                               route_lanes_policy=policies['outside_route_lanes_infraction'])
