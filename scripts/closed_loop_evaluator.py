"""Shared evaluator instrumentation for standard and feedback entry points."""

import runpy
import os
import sys
import time

from Bench2DriveZoo.team_code import eval_telemetry
from Bench2DriveZoo.team_code import live_events
from Bench2DriveZoo.team_code.collision_stop import SustainedCollisionStop
from leaderboard.scenarios.scenario_manager import ScenarioManager
from leaderboard.autoagents.agent_wrapper import AgentWrapper
from leaderboard.envs.sensor_interface import SensorInterface
from srunner.scenariomanager.scenarioatomics.atomic_criteria import CollisionTest, Criterion, RouteCompletionTest
from srunner.scenariomanager.traffic_events import TrafficEvent

feedback_mode = len(sys.argv) > 1 and sys.argv[1] == '--feedback-pipeline'
if feedback_mode:
    del sys.argv[1]
    from Bench2DriveZoo.feedback_pipeline.carla_triggers import adapter_from_environment
    from srunner.scenariomanager.carla_data_provider import CarlaDataProvider
    from srunner.scenariomanager.timer import GameTime

# Bench2Drive hardcodes GNSS/IMU noise magnitudes in AgentWrapper. CARLA 0.9.15
# exposes a per-sensor `noise_seed` blueprint attribute, so set it as sensors
# are created without modifying the adjacent Bench2Drive checkout.
sensor_noise_seed = int(os.environ.get('CARLA_SENSOR_NOISE_SEED', '0'))
original_preprocess_sensor_spec = AgentWrapper._preprocess_sensor_spec


def preprocess_sensor_spec_with_noise_seed(self, sensor_spec):
    type_, id_, transform, attributes = original_preprocess_sensor_spec(self, sensor_spec)
    if type_ == 'sensor.other.gnss':
        attributes['noise_seed'] = str(sensor_noise_seed)
    elif type_ == 'sensor.other.imu':
        attributes['noise_seed'] = str(sensor_noise_seed + 1)
    return type_, id_, transform, attributes


AgentWrapper._preprocess_sensor_spec = preprocess_sensor_spec_with_noise_seed

original_criterion_init = Criterion.__init__
original_set_dict = TrafficEvent.set_dict


def emit_feedback_event(event, change):
    if feedback_triggers is None:
        return
    if event.get_type().name not in ('COLLISION_STATIC', 'COLLISION_VEHICLE',
                                     'COLLISION_PEDESTRIAN', 'OUTSIDE_ROUTE_LANES_INFRACTION'):
        return
    snapshot = CarlaDataProvider.get_world().get_snapshot()
    frame = GameTime.get_frame() if change == 'updated' else event.get_frame()
    feedback_triggers.benchmark_event(event, change, frame,
                                      snapshot.timestamp.elapsed_seconds)


class FeedbackEventList(live_events.EventList):
    def append(self, event):
        super().append(event)
        emit_feedback_event(event, 'created')


def criterion_init_with_events(self, *args, **kwargs):
    original_criterion_init(self, *args, **kwargs)
    self.events = FeedbackEventList(self.name) if feedback_mode else live_events.EventList(self.name)


def set_dict_with_events(self, dictionary):
    original_set_dict(self, dictionary)
    criterion = getattr(self, '_live_event_criterion', None)
    if criterion is not None:
        live_events.write_event(self, criterion, 'updated')
        if feedback_mode:
            emit_feedback_event(self, 'updated')


Criterion.__init__ = criterion_init_with_events
TrafficEvent.set_dict = set_dict_with_events

collision_stop = SustainedCollisionStop(int(os.environ.get('SUSTAINED_COLLISION_FRAMES', '1')))
feedback_triggers = adapter_from_environment() if feedback_mode else None
original_collision_callback = CollisionTest._count_collisions
original_load_scenario = ScenarioManager.load_scenario
def collision_callback_with_stop(self, event):
    previous_count = len(self.events)
    original_collision_callback(self, event)
    accepted = any(e.get_type().name in ('COLLISION_STATIC', 'COLLISION_VEHICLE', 'COLLISION_PEDESTRIAN')
                   for e in self.events[previous_count:])
    collision_stop.observe(event.other_actor.id, event.frame, accepted)


def load_scenario_with_stop_reset(self, *args, **kwargs):
    collision_stop.reset()
    result = original_load_scenario(self, *args, **kwargs)
    if feedback_triggers is not None:
        feedback_triggers.reset({'route_index': self.route_index,
                                 'repetition': self.repetition_number})
    return result


CollisionTest._count_collisions = collision_callback_with_stop
ScenarioManager.load_scenario = load_scenario_with_stop_reset

def instrument(cls, method, label):
    original = getattr(cls, method)
    def timed(*args, **kwargs):
        with eval_telemetry.measure(label):
            return original(*args, **kwargs)
    setattr(cls, method, timed)


original_tick_scenario = ScenarioManager._tick_scenario


def tick_scenario_with_stop(self):
    with eval_telemetry.measure('simulation_step'):
        result = original_tick_scenario(self)
    stop = collision_stop.take_stop()
    if stop is not None:
        live_events.write_stop(stop)
        self._running = False
    return result


ScenarioManager._tick_scenario = tick_scenario_with_stop
instrument(AgentWrapper, '__call__', 'agent_total')
instrument(SensorInterface, 'get_data', 'sensor_wait')

stop_monitor = eval_telemetry.start_monitor(
    os.path.join(os.environ['SAVE_PATH'], 'telemetry.jsonl'))

original_update = RouteCompletionTest.update
original_terminate = RouteCompletionTest.terminate


def report_progress(criterion):
    print("[route progress] {:.2f}% complete".format(criterion.actual_value), flush=True)


def update_with_progress(criterion):
    result = original_update(criterion)
    now = time.monotonic()
    if now - getattr(criterion, "_progress_log_time", float("-inf")) >= 30:
        report_progress(criterion)
        criterion._progress_log_time = now
    return result


def terminate_with_progress(criterion, new_status):
    result = original_terminate(criterion, new_status)
    report_progress(criterion)
    return result


RouteCompletionTest.update = update_with_progress
RouteCompletionTest.terminate = terminate_with_progress

evaluator = sys.argv[1]
sys.argv = sys.argv[1:]
try:
    runpy.run_path(evaluator, run_name="__main__")
finally:
    if stop_monitor:
        stop_monitor.set()
