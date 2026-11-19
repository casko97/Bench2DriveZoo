"""Capture VAD observations and CARLA state without altering agent control."""

import json
import hashlib
import math
import os
from pathlib import Path
from functools import lru_cache
import uuid

from .contracts import CollectionRun, TrainingRound
from .window_recorder import AsyncWindowRecorder, CapturedFrame

CAMERAS = ('CAM_FRONT', 'CAM_FRONT_LEFT', 'CAM_FRONT_RIGHT',
           'CAM_BACK', 'CAM_BACK_LEFT', 'CAM_BACK_RIGHT', 'bev')
SENSORS = ('GPS', 'IMU', 'SPEED')
RECORD_FLAGS = ('ego_state', 'actor_states', 'traffic_lights', 'policy_outputs', 'previous_controls')


@lru_cache(maxsize=8)
def _file_digest(path, size, mtime_ns):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint_identity(path):
    if not path:
        return {'path': path, 'sha256': None}
    resolved = os.path.realpath(path)
    stat = os.stat(resolved)
    return {'path': path, 'resolved_path': resolved, 'size_bytes': stat.st_size,
            'sha256': _file_digest(resolved, stat.st_size, stat.st_mtime_ns)}


def plain(value):
    if hasattr(value, 'tolist'):
        return plain(value.tolist())
    if isinstance(value, dict):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def vector(value):
    return {'x': value.x, 'y': value.y, 'z': value.z}


def state(actor):
    transform = actor.get_transform()
    box = actor.bounding_box
    return {'id': actor.id, 'type': actor.type_id, 'location': vector(transform.location),
            'rotation_degrees': {'pitch': transform.rotation.pitch, 'yaw': transform.rotation.yaw,
                                 'roll': transform.rotation.roll},
            'velocity_mps': vector(actor.get_velocity()),
            'acceleration_mps2': vector(actor.get_acceleration()),
            'angular_velocity_degps': vector(actor.get_angular_velocity()),
            'bounding_box': {'location': vector(box.location), 'extent': vector(box.extent),
                             'rotation_degrees': {'pitch': box.rotation.pitch, 'yaw': box.rotation.yaw,
                                                  'roll': box.rotation.roll}}}


def config_from_environment():
    path = os.environ.get('FEEDBACK_WINDOW_CONFIG', str(Path(__file__).with_name('window_config.json')))
    with open(path, encoding='utf-8') as handle:
        config = json.load(handle)
    fields = {'before_seconds', 'after_seconds', 'max_buffer_mib', 'writer_queue_frames',
              'max_pending_events', 'actor_radius_m', 'record'}
    if not isinstance(config, dict) or set(config) != fields:
        raise ValueError('Window config must contain exactly: {}'.format(', '.join(sorted(fields))))
    for key, value in config.items():
        if key == 'record':
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('{} must be a finite number'.format(key))
        if value < 0 or (key not in ('before_seconds', 'after_seconds') and value == 0):
            raise ValueError('{} must be positive (durations can be zero)'.format(key))
        if key in ('writer_queue_frames', 'max_pending_events') and not isinstance(value, int):
            raise ValueError('{} must be an integer'.format(key))
    record = config['record']
    if not isinstance(record, dict) or set(record) != set(RECORD_FLAGS) | {'cameras', 'sensors'}:
        raise ValueError('record must specify cameras, sensors, and all recording flags')
    for key, allowed in (('cameras', CAMERAS), ('sensors', SENSORS)):
        values = record[key]
        if (not isinstance(values, list) or any(not isinstance(v, str) or v not in allowed for v in values)
                or len(values) != len(set(values))):
            raise ValueError('{} must be a list of unique supported names: {}'.format(key, ', '.join(allowed)))
    for key in RECORD_FLAGS:
        if not isinstance(record[key], bool):
            raise ValueError('record.{} must be a boolean'.format(key))
    return config


class CarlaWindowCapture:
    def __init__(self, root, agent, scenario, route_index, repetition, world, ego, config, trigger_monitor):
        self.world, self.ego, self.agent, self.config = world, ego, agent, config
        run_id = uuid.uuid4().hex
        round_id = os.environ.get('FEEDBACK_ROUND_ID') or uuid.uuid4().hex
        checkpoint = getattr(agent, 'ckpt_path', None)
        round_data = TrainingRound(round_id, policy_checkpoint=checkpoint_identity(checkpoint),
                                   configuration={'window': config,
                                                  'trigger': {'global_mode': trigger_monitor.global_mode,
                                                      'reasons': {name: {'mode': policy.mode,
                                                                         'cooldown_seconds': policy.cooldown}
                                                                  for name, policy in trigger_monitor.policies.items()}},
                                                  'policy_config': getattr(agent, 'config_path', None),
                                                  'sensors': plain(agent.sensors())})
        route = {'index': route_index, 'repetition': repetition, 'routes_file': os.environ.get('ROUTES'),
                 'global_plan_world': [plain_transform(item[0]) for item in getattr(agent, '_global_plan_world_coord', [])]}
        run_data = CollectionRun(run_id, round_id=round_id, route=route,
            scenario={'name': getattr(scenario, 'name', None)},
            simulator={'map': world.get_map().name, 'fixed_delta_seconds': world.get_settings().fixed_delta_seconds},
            seeds={'traffic_manager': os.environ.get('TRAFFIC_MANAGER_SEED', '0'),
                   'gnss_imu': os.environ.get('CARLA_SENSOR_NOISE_SEED', '0')})
        self.recorder = AsyncWindowRecorder(root, round_data, run_data,
            before=config['before_seconds'], after=config['after_seconds'],
            max_bytes=int(config['max_buffer_mib'] * 1024 * 1024),
            queue_size=config['writer_queue_frames'], max_pending=config['max_pending_events'])

    def capture(self, input_data, previous_controls):
        snapshot = self.world.get_snapshot()
        frame = snapshot.frame
        sensors, missing, sensor_metadata = {}, [], {}
        record = self.config['record']
        for name in record['cameras']:
            if name not in input_data:
                missing.append(name + ': absent')
                continue
            number, image = input_data[name]
            if number != frame:
                missing.append('{}: sensor frame {} != {}'.format(name, number, frame))
            sensors[name] = (number, image.copy())
        for name in record['sensors']:
            if name not in input_data:
                missing.append(name + ': absent')
            else:
                number, value = input_data[name]
                sensor_metadata[name] = {'frame': number, 'value': plain(value)}
                if number != frame:
                    missing.append('{}: sensor frame {} != {}'.format(name, number, frame))
        ego = state(self.ego) if record['ego_state'] else {}
        origin = self.ego.get_location()
        actors, lights = [], []
        for actor in self.world.get_actors() if record['actor_states'] or record['traffic_lights'] else []:
            if actor.id == self.ego.id:
                continue
            try:
                if actor.get_location().distance(origin) > self.config['actor_radius_m']:
                    continue
                if record['actor_states'] and actor.type_id.startswith(('vehicle.', 'walker.pedestrian.', 'static.')) and hasattr(actor, 'bounding_box'):
                    actors.append(state(actor))
                elif record['traffic_lights'] and actor.type_id.startswith('traffic.traffic_light'):
                    lights.append({'id': actor.id, 'location': vector(actor.get_location()),
                                   'state': str(actor.get_state())})
            except RuntimeError:
                # The actor disappeared between enumeration and inspection.
                missing.append('actor {} disappeared'.format(actor.id))
        context = {'sensor_values': sensor_metadata, 'temporal_bev_captured': False,
                   'policy_checkpoint': getattr(self.agent, 'ckpt_path', None)}
        if record['policy_outputs']:
            context['planned_trajectories'] = plain(getattr(self.agent, 'pid_metadata', {}))
        if record['previous_controls']:
            context['previous_controls'] = previous_controls
        self.recorder.frame(CapturedFrame(frame, snapshot.timestamp.elapsed_seconds, ego,
                                          actors, lights, context, sensors, missing))

    def trigger(self, event):
        self.recorder.trigger(event)

    def close(self):
        self.recorder.close()
        print('[feedback windows] dropped frames: {}'.format(self.recorder.dropped_frames), flush=True)


def plain_transform(transform):
    return {'location': vector(transform.location),
            'rotation_degrees': {'pitch': transform.rotation.pitch, 'yaw': transform.rotation.yaw,
                                 'roll': transform.rotation.roll}}


def control_dict(control):
    return {'steer': control.steer, 'throttle': control.throttle, 'brake': control.brake,
            'reverse': control.reverse, 'hand_brake': control.hand_brake, 'gear': control.gear}
