"""Run the Bench2Drive evaluator and report its route completion criterion."""

import runpy
import sys
import time

from Bench2DriveZoo.team_code import eval_telemetry
from leaderboard.scenarios.scenario_manager import ScenarioManager
from leaderboard.autoagents.agent_wrapper import AgentWrapper
from leaderboard.envs.sensor_interface import SensorInterface
from srunner.scenariomanager.scenarioatomics.atomic_criteria import RouteCompletionTest

def instrument(cls, method, label):
    original = getattr(cls, method)
    def timed(*args, **kwargs):
        with eval_telemetry.measure(label):
            return original(*args, **kwargs)
    setattr(cls, method, timed)


instrument(ScenarioManager, '_tick_scenario', 'simulation_step')
instrument(AgentWrapper, '__call__', 'agent_total')
instrument(SensorInterface, 'get_data', 'sensor_wait')

stop_monitor = eval_telemetry.start_monitor(
    __import__('os').path.join(__import__('os').environ['SAVE_PATH'], 'telemetry.jsonl'))

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
