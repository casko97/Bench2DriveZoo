import hashlib
import json
import threading

import cv2
import numpy as np
import pytest

from feedback_pipeline import CollectionRun, FeedbackStore, TrainingRound
from feedback_pipeline.carla_windows import CarlaWindowCapture, checkpoint_identity, config_from_environment
from feedback_pipeline.window_recorder import AsyncWindowRecorder, CapturedFrame, EncodedFrame, WindowAssembler


def frame(number, missing=None, payload=b'img'):
    return EncodedFrame(number, number / 10, {'x': number}, [], [], {},
                        {'camera': (number, payload)}, missing or [])


def event(number):
    return {'frame': number, 'simulation_time_seconds': number / 10,
            'type': 'collision', 'evidence': {'source': 'COLLISION_STATIC'}}


def test_before_after_and_late_trigger_match_by_frame():
    results = []
    assembler = WindowAssembler(.2, .2, 10000, 4, lambda *args: results.append(args))
    for i in range(7):
        assembler.frame(frame(i))
    assembler.trigger(event(5))
    assembler.frame(frame(7))
    assert len(results) == 1
    _, frames, anchor, before, after, reason = results[0]
    assert [item.number for item in frames] == [3, 4, 5, 6, 7]
    assert anchor == .5 and before == pytest.approx(.2) and after == pytest.approx(.2)
    assert reason is None


def test_trigger_can_arrive_before_its_frame():
    results = []
    assembler = WindowAssembler(.1, .1, 10000, 4, lambda *args: results.append(args))
    assembler.frame(frame(1))
    assembler.trigger(event(2))
    assembler.frame(frame(2))
    assembler.frame(frame(3))
    assert [item.number for item in results[0][1]] == [1, 2, 3]
    assert results[0][-1] is None


def test_route_end_missing_frames_and_sensor_gaps_are_incomplete():
    results = []
    assembler = WindowAssembler(.1, .2, 10000, 4, lambda *args: results.append(args))
    assembler.frame(frame(1))
    assembler.frame(frame(2))
    assembler.trigger(event(2))
    assembler.frame(frame(4))
    assert results[0][-1] == 'missing simulation frames'
    assembler.frame(frame(5, missing=['camera absent']))
    assembler.trigger(event(5))
    assembler.finish()
    assert results[1][-1] == 'route ended before window was complete'


def test_buffer_budget_and_pending_limit_are_bounded():
    results = []
    assembler = WindowAssembler(1, 1, 4, 1, lambda *args: results.append(args))
    assembler.frame(frame(1, payload=b'1234'))
    assembler.frame(frame(2, payload=b'5678'))
    assert assembler.buffer_bytes == 4 and [f.number for f in assembler.buffer] == [2]
    assembler.trigger(event(2))
    assembler.trigger(event(2))
    assert results[0][-1] == 'pending event limit reached'
    assert len(assembler.pending) == 1


def test_pending_windows_do_not_hold_unbounded_evicted_history():
    results = []
    assembler = WindowAssembler(.1, 1, 8, 4, lambda *args: results.append(args))
    assembler.frame(frame(1, payload=b'1234'))
    assembler.frame(frame(2, payload=b'5678'))
    assembler.trigger(event(2))
    assembler.frame(frame(3, payload=b'9012'))
    assert results[0][-1] == 'window buffer memory limit reached'
    assert not assembler.pending and assembler.buffer_bytes <= 8


def test_async_recorder_persists_event_frames_and_anchor(tmp_path):
    round_data = TrainingRound('round')
    run_data = CollectionRun('run', round_id='round')
    recorder = AsyncWindowRecorder(tmp_path, round_data, run_data, before=.1, after=.1, queue_size=10)
    for number in (1, 2):
        image = np.full((2, 2, 4), number, dtype=np.uint8)
        recorder.frame(CapturedFrame(number, number / 10, {'x': number}, [], [],
            {'temporal_bev_captured': False}, {'CAM_FRONT': (number, image)}))
    recorder.trigger(event(2))
    recorder.frame(CapturedFrame(3, .3, {'x': 3}, [], [], {},
                                 {'CAM_FRONT': (3, np.zeros((2, 2, 4), dtype=np.uint8))}))
    recorder.close()
    with FeedbackStore(tmp_path) as store:
        window = store.get(store.list_ids('event_window')[0])
        assert window.status == 'complete'
        assert window.frame_ids == ['run:1', 'run:2', 'run:3']
        assert store.get(window.trigger_id).frame_id == 'run:2'
        data = store.read_artifact(store.get('run:1').artifacts['CAM_FRONT'])
        decoded = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        assert np.array_equal(decoded, np.full((2, 2, 4), 1, dtype=np.uint8))
        anchor = store.get(store.list_ids('anchor')[0])
        assert anchor.frame_id == 'run:1' and anchor.metadata['replay_verified'] is False


def test_async_recorder_persists_missing_trigger_frame_as_failed(tmp_path):
    recorder = AsyncWindowRecorder(tmp_path, TrainingRound('r'), CollectionRun('run', round_id='r'),
                                   before=1, after=1)
    recorder.trigger(event(42))
    recorder.close()
    with FeedbackStore(tmp_path) as store:
        window = store.get(store.list_ids('event_window')[0])
        assert window.status == 'failed' and window.reason
        placeholder = store.get(store.get(window.trigger_id).frame_id)
        assert placeholder.status == 'failed' and placeholder.metadata['placeholder'] is True


def test_saturated_writer_drops_frames_without_blocking(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = AsyncWindowRecorder._encode

    def slow_encode(item):
        entered.set()
        assert release.wait(5)
        return original(item)

    monkeypatch.setattr(AsyncWindowRecorder, '_encode', staticmethod(slow_encode))
    recorder = AsyncWindowRecorder(tmp_path, TrainingRound('r'), CollectionRun('run', round_id='r'),
                                   queue_size=1)
    item = CapturedFrame(1, .1, {}, [], [], {}, {})
    try:
        assert recorder.frame(item)
        assert entered.wait(5)
        assert recorder.frame(item)
        assert not recorder.frame(item)
        assert recorder.dropped_frames == 1
    finally:
        release.set()
        recorder.close()


def test_existing_round_cannot_change_its_checkpoint(tmp_path):
    first = AsyncWindowRecorder(tmp_path, TrainingRound('r', policy_checkpoint={'sha256': 'a'}),
                                CollectionRun('run-1', round_id='r'))
    first.close()
    second = AsyncWindowRecorder(tmp_path, TrainingRound('r', policy_checkpoint={'sha256': 'b'}),
                                 CollectionRun('run-2', round_id='r'))
    with pytest.raises(RuntimeError, match='recorder failed'):
        second.close()
    with FeedbackStore(tmp_path) as store:
        assert store.get('r').policy_checkpoint == {'sha256': 'a'}
        assert store.list_ids('collection_run') == ['run-1']


def test_config_rejects_unknown_and_invalid_values(tmp_path, monkeypatch):
    config = {'before_seconds': 1, 'after_seconds': 1, 'max_buffer_mib': 2,
              'writer_queue_frames': 2, 'max_pending_events': 4, 'actor_radius_m': 60,
              'record': {'cameras': ['bev'], 'sensors': [], 'ego_state': True,
                         'actor_states': True, 'traffic_lights': False,
                         'policy_outputs': True, 'previous_controls': False}}
    path = tmp_path / 'window.json'
    monkeypatch.setenv('FEEDBACK_WINDOW_CONFIG', str(path))
    path.write_text(json.dumps(config))
    assert config_from_environment() == config
    config['writer_queue_frames'] = 0
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError):
        config_from_environment()
    config['writer_queue_frames'] = 2
    for cameras in (['bev', 'bev'], ['unknown']):
        config['record']['cameras'] = cameras
        path.write_text(json.dumps(config))
        with pytest.raises(ValueError, match='cameras'):
            config_from_environment()
    config['record']['cameras'] = []
    config['record']['ego_state'] = 1
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='ego_state'):
        config_from_environment()


def test_checkpoint_identity_includes_content_hash(tmp_path):
    path = tmp_path / 'policy.pth'
    path.write_bytes(b'checkpoint')
    identity = checkpoint_identity(str(path))
    assert identity['size_bytes'] == 10
    assert identity['sha256'] == hashlib.sha256(b'checkpoint').hexdigest()


def test_capture_selects_only_configured_data():
    from types import SimpleNamespace
    captured = []
    capture = CarlaWindowCapture.__new__(CarlaWindowCapture)
    capture.config = {'actor_radius_m': 10, 'record': {'cameras': ['bev'], 'sensors': [],
        'ego_state': False, 'actor_states': False, 'traffic_lights': False,
        'policy_outputs': False, 'previous_controls': False}}
    capture.world = SimpleNamespace(get_snapshot=lambda: SimpleNamespace(
        frame=4, timestamp=SimpleNamespace(elapsed_seconds=0.2)))
    capture.ego = SimpleNamespace(get_location=lambda: None)
    capture.agent = SimpleNamespace(ckpt_path='policy')
    capture.recorder = SimpleNamespace(frame=captured.append)
    image = np.zeros((2, 2, 4), dtype=np.uint8)
    capture.capture({'bev': (4, image), 'CAM_FRONT': (4, image)}, [{'steer': 0}])
    result = captured[0]
    assert list(result.sensors) == ['bev']
    assert result.missing == [] and result.ego == {} and result.actors == []
    assert 'previous_controls' not in result.context and 'planned_trajectories' not in result.context
    assert result.sensors['bev'][1] is not image
