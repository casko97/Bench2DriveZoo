from types import SimpleNamespace
import pytest
from feedback_pipeline.pdm_lite import PdmLiteAdapter


class Agent:
    def __init__(self, config, index):
        self.calls = [('init', config, index)]
        self.config = SimpleNamespace(steer_noise=0.001)
    def set_global_plan(self, gps, world):
        self.calls.append(('route', gps, world))
    def setup(self, config, index, tm):
        self.calls.append(('setup', config, index, tm))
    def run_step(self, data, timestamp):
        return SimpleNamespace(steer=0.1, throttle=0.5, brake=0.0)
    def destroy(self):
        self.calls.append(('destroy',))


def make_adapter(provider, **changes):
    args = dict(config_path='config', route_index=1, world='world', ego='ego',
                gps_route=[1, 2], world_route=[3, 4], scenario_state=[],
                provenance={'revision': 'abc'})
    args.update(changes)
    return PdmLiteAdapter(Agent, provider, **args)


def provider():
    return SimpleNamespace(active_scenarios=None, get_world=lambda: 'world',
                           get_hero_actor=lambda: 'ego')


def test_setup_order_and_control():
    adapter = make_adapter(provider())
    assert [call[0] for call in adapter.agent.calls] == ['init', 'route', 'setup']
    assert adapter.provenance['steer_noise'] == 0.0
    assert adapter.run_step({'imu': (1, [0.0])}, 1).throttle == .5
    adapter.close()
    assert adapter.agent.calls[-1] == ('destroy',)


def test_requires_scenario_and_matching_provider():
    with pytest.raises(ValueError, match='scenario'):
        make_adapter(provider(), scenario_state=None)
    with pytest.raises(ValueError, match='provider'):
        make_adapter(provider(), ego='other')
    with pytest.raises(ValueError, match='routes'):
        make_adapter(provider(), gps_route=[])


def test_rejects_missing_imu_and_invalid_control():
    adapter = make_adapter(provider())
    with pytest.raises(ValueError, match='IMU'):
        adapter.run_step({}, 1)
    adapter.agent.run_step = lambda *_: SimpleNamespace(steer=float('nan'), throttle=0, brake=0)
    with pytest.raises(ValueError, match='steer'):
        adapter.run_step({'imu': (1, [0.0])}, 1)
