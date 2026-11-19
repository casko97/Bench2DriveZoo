"""Simulator-independent collision and route-lane trigger deduplication."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TriggerPolicy:
    mode: str = 'multiple'
    cooldown: float = 2.0

    def __post_init__(self):
        if self.mode not in ('once', 'multiple'):
            raise ValueError('Trigger mode must be once or multiple')
        if not math.isfinite(self.cooldown) or self.cooldown < 0:
            raise ValueError('Cooldown must be finite and non-negative')


class TriggerMonitor:
    """Apply independent per-reason policies to accepted benchmark events."""

    def __init__(self, cooldown=2.0, collision_policy=None, route_lanes_policy=None):
        self.policies = {
            'collision': collision_policy or TriggerPolicy('multiple', cooldown),
            'outside_route_lanes_infraction': route_lanes_policy or TriggerPolicy('once', cooldown),
        }
        self.reset()

    def reset(self):
        self._emitted_reasons = set()
        self._last_emitted = {}

    def _observe(self, key, frame, simulation_time, evidence):
        reason = key[0]
        policy = self.policies[reason]
        if policy.mode == 'once' and reason in self._emitted_reasons:
            return None
        if simulation_time - self._last_emitted.get(key, float('-inf')) < policy.cooldown:
            return None
        self._last_emitted[key] = simulation_time
        self._emitted_reasons.add(reason)
        return {'type': key[0], 'frame': frame, 'simulation_time_seconds': simulation_time,
                'evidence': evidence}

    def collision(self, frame, simulation_time, actor_id, evidence):
        # In multiple mode collision cooldown applies independently per other actor.
        key = ('collision', str(actor_id))
        return self._observe(key, frame, simulation_time, evidence)

    def route_lanes_infraction(self, frame, simulation_time, evidence):
        # Multiple mode emits cumulative benchmark updates, not separate excursions.
        return self._observe(('outside_route_lanes_infraction', ''),
                             frame, simulation_time, evidence)

