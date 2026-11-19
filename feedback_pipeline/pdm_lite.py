"""Isolated-process adapter for a pinned CARLA Garage PDM-Lite agent.

Run this adapter in a fresh Python process using Garage's own leaderboard and
scenario runner on PYTHONPATH. It deliberately does not manufacture scenario
state or treat an import as proof of takeover feasibility.
"""
import math


class PdmLiteAdapter:
    def __init__(self, agent_class, provider, *, config_path, route_index,
                 world, ego, gps_route, world_route, scenario_state, provenance,
                 traffic_manager=None):
        if not gps_route or not world_route or len(gps_route) != len(world_route):
            raise ValueError('non-empty, aligned dense GPS and world routes are required')
        if scenario_state is None or not isinstance(scenario_state, list):
            raise ValueError('explicit Garage-compatible active scenario state is required')
        if not hasattr(provider, 'active_scenarios'):
            raise RuntimeError('Garage scenario provider with active_scenarios is required')
        if provider.get_world() != world or provider.get_hero_actor() != ego:
            raise ValueError('provider world and hero must already match the continuation')
        if not isinstance(provenance, dict) or not provenance.get('revision'):
            raise ValueError('expert revision provenance is required')
        self.provenance = dict(provenance)
        self.provider = provider
        # Scenario objects belong to the live scenario manager, not reconstructed
        # copies; the caller is responsible for their lifetime and compatibility.
        provider.active_scenarios = scenario_state
        self.agent = agent_class(config_path, route_index)
        self.agent.set_global_plan(gps_route, world_route)
        self.agent.setup(config_path, route_index, traffic_manager)
        # Disable upstream collection noise for reproducible feedback and to
        # prevent noise pushing a saturated steering command beyond [-1, 1].
        self.agent.config.steer_noise = 0.0
        self.provenance['steer_noise'] = 0.0

    def run_step(self, input_data, timestamp):
        if 'imu' not in input_data:
            raise ValueError('PDM-Lite requires synchronized IMU input')
        control = self.agent.run_step(input_data, timestamp)
        for name, low, high in (('steer', -1, 1), ('throttle', 0, 1), ('brake', 0, 1)):
            value = getattr(control, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
                raise ValueError('invalid expert control: {}={!r}'.format(name, value))
        return control

    def close(self):
        self.agent.destroy()
