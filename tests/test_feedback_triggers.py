import json
from types import SimpleNamespace

import pytest

from feedback_pipeline.carla_triggers import CarlaTriggerAdapter, adapter_from_environment, load_trigger_config
from feedback_pipeline.triggers import TriggerMonitor, TriggerPolicy


def benchmark_event(event_type, details, message='benchmark event'):
    return SimpleNamespace(get_type=lambda: SimpleNamespace(name=event_type),
                           get_dict=lambda: details, get_message=lambda: message)


def test_route_lanes_emits_once_per_route_despite_cumulative_updates():
    monitor = TriggerMonitor(cooldown=2)
    event = monitor.route_lanes_infraction(10, 1.0, {'source': 'criterion'})
    assert event == {'type': 'outside_route_lanes_infraction', 'frame': 10, 'simulation_time_seconds': 1.0,
                     'evidence': {'source': 'criterion'}}
    assert monitor.route_lanes_infraction(11, 1.1, {}) is None
    assert monitor.route_lanes_infraction(14, 3.1, {}) is None
    monitor.reset()
    assert monitor.route_lanes_infraction(16, 3.3, {})['frame'] == 16


def test_collision_cooldown_per_actor_and_reset():
    monitor = TriggerMonitor(cooldown=2)
    assert monitor.collision(1, 1, 100, {'actor_id': 100})['type'] == 'collision'
    assert monitor.collision(2, 1.1, 100, {}) is None
    assert monitor.collision(2, 1.1, 101, {}) is not None
    assert monitor.collision(40, 3.0, 100, {}) is not None
    monitor.reset()
    assert monitor.collision(1, 0.1, 100, {}) is not None


def test_once_mode_is_per_reason_not_per_collision_actor():
    monitor = TriggerMonitor(collision_policy=TriggerPolicy('once', 0),
                             route_lanes_policy=TriggerPolicy('multiple', 1))
    assert monitor.collision(1, 0, 100, {}) is not None
    assert monitor.collision(2, 2, 101, {}) is None
    assert monitor.route_lanes_infraction(2, 2, {}) is not None
    assert monitor.route_lanes_infraction(3, 2.5, {}) is None
    assert monitor.route_lanes_infraction(4, 3.0, {}) is not None
    monitor.reset()
    assert monitor.collision(1, 0, 101, {}) is not None


def test_independent_cooldowns_and_zero_lane_cooldown():
    monitor = TriggerMonitor(collision_policy=TriggerPolicy('multiple', 5),
                             route_lanes_policy=TriggerPolicy('multiple', 0))
    assert monitor.collision(1, 1, 10, {}) is not None
    assert monitor.collision(2, 2, 10, {}) is None
    assert monitor.route_lanes_infraction(2, 2, {}) is not None
    assert monitor.route_lanes_infraction(3, 2, {}) is not None
    assert monitor.collision(4, 6, 10, {}) is not None


@pytest.mark.parametrize('value', [-1, float('nan'), float('inf')])
def test_invalid_cooldown_rejected(value):
    with pytest.raises(ValueError):
        TriggerMonitor(cooldown=value)


def test_invalid_mode_rejected():
    with pytest.raises(ValueError, match='once or multiple'):
        TriggerPolicy('unlimited', 1)


def test_adapter_logs_source_timing_and_separate_routes(tmp_path):
    path = tmp_path / 'feedback_triggers.jsonl'
    adapter = CarlaTriggerAdapter(str(path), cooldown=2)
    adapter.reset({'route_index': 3, 'repetition': 0})
    lane = benchmark_event('OUTSIDE_ROUTE_LANES_INFRACTION', {'distance': 0.5, 'percentage': 2})
    adapter.benchmark_event(lane, 'created', 41, 2.05)
    adapter.benchmark_event(lane, 'updated', 42, 2.1)
    actor = SimpleNamespace(id=9, type_id='static.fence')
    adapter.benchmark_event(benchmark_event('COLLISION_STATIC', {'other_actor': actor}), 'created', 43, 2.15)
    adapter.reset({'route_index': 4, 'repetition': 0})
    adapter.benchmark_event(lane, 'updated', 1, 0.1)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [row['type'] for row in rows] == ['outside_route_lanes_infraction', 'collision', 'outside_route_lanes_infraction']
    assert rows[0]['frame'] == 42 and rows[0]['simulation_time_seconds'] == 2.1
    assert rows[1]['evidence']['source'] == 'COLLISION_STATIC'
    assert rows[1]['evidence']['actor_type'] == 'static.fence'
    assert rows[2]['route']['route_index'] == 4


@pytest.mark.parametrize('actor_type,event_type', [('static.fence', 'COLLISION_STATIC'),
    ('vehicle.tesla.model3', 'COLLISION_VEHICLE'), ('walker.pedestrian.0001', 'COLLISION_PEDESTRIAN')])
def test_benchmark_collision_events_generate_triggers(tmp_path, actor_type, event_type):
    path = tmp_path / 'feedback_triggers.jsonl'
    adapter = CarlaTriggerAdapter(str(path), cooldown=2)
    adapter.reset({'route_index': 0, 'repetition': 0})
    actor = SimpleNamespace(id=21, type_id=actor_type)
    adapter.benchmark_event(benchmark_event(event_type, {'other_actor': actor}), 'created', 7, 0.35)
    row = json.loads(path.read_text())
    assert row['type'] == 'collision'
    assert row['evidence']['actor_type'] == actor_type
    assert row['evidence']['source'] == event_type


def test_unrelated_events_and_inappropriate_changes_are_ignored(tmp_path):
    path = tmp_path / 'feedback_triggers.jsonl'
    adapter = CarlaTriggerAdapter(str(path), cooldown=2)
    adapter.benchmark_event(benchmark_event('COLLISION_VEHICLE', {}), 'updated', 1, 0.1)
    adapter.benchmark_event(benchmark_event('MIN_SPEED_INFRACTION', {}), 'created', 2, 0.2)
    assert not path.exists()


def test_adapter_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv('FEEDBACK_TRIGGERS', raising=False)
    assert adapter_from_environment() is None
    monkeypatch.setenv('FEEDBACK_TRIGGERS', '1')
    monkeypatch.setenv('SAVE_PATH', str(tmp_path))
    monkeypatch.delenv('FEEDBACK_TRIGGER_CONFIG', raising=False)
    monkeypatch.setenv('FEEDBACK_COLLISION_MODE', 'once')
    monkeypatch.setenv('FEEDBACK_TRIGGER_COOLDOWN_SECONDS', '99')
    adapter = adapter_from_environment()
    assert adapter.monitor.policies['collision'] == TriggerPolicy('multiple', 2)
    assert adapter.monitor.policies['outside_route_lanes_infraction'] == TriggerPolicy('once', 2)


def test_per_reason_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv('FEEDBACK_TRIGGERS', '1')
    monkeypatch.setenv('SAVE_PATH', str(tmp_path))
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'collision': {'mode': 'once', 'cooldown_seconds': 0.5},
        'outside_route_lanes_infraction': {'mode': 'multiple', 'cooldown_seconds': 3}}))
    monkeypatch.setenv('FEEDBACK_TRIGGER_CONFIG', str(config))
    monitor = adapter_from_environment().monitor
    assert monitor.policies['collision'] == TriggerPolicy('once', 0.5)
    assert monitor.policies['outside_route_lanes_infraction'] == TriggerPolicy('multiple', 3)


@pytest.mark.parametrize('change', [
    lambda config: config.pop('collision'),
    lambda config: config.update({'typo': {}}),
    lambda config: config['collision'].update({'mode': 'typo'}),
    lambda config: config['collision'].update({'cooldown_seconds': -1}),
    lambda config: config['collision'].update({'cooldown_seconds': True}),
    lambda config: config['collision'].update({'cooldown_seconds': '2'}),
    lambda config: config['collision'].update({'unexpected': 1}),
])
def test_invalid_config_rejected(tmp_path, change):
    config = {'collision': {'mode': 'once', 'cooldown_seconds': 1},
              'outside_route_lanes_infraction': {'mode': 'multiple', 'cooldown_seconds': 2}}
    change(config)
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        load_trigger_config(path)
