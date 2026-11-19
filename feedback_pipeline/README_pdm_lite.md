# PDM-Lite feasibility work

The adapter targets CARLA Garage revision `48e6a6dbcb133220333bd65e242fbc2b492bb15b`
from its `leaderboard_2` branch. The worktree uses an isolated copy under
`downloads/carla_garage` and the `b2d_zoo-pdm-light.venv` environment. The
Garage checkout has an MIT top-level license; individual dependencies and
components require their own license review before redistribution.

PDM-Lite must run in a separate Python process with Garage's `leaderboard_autopilot`
and `scenario_runner_autopilot` first on its import path. The adapter requires
an already initialized Garage data provider, the live hero and world, dense GPS
and world routes, synchronized IMU data and explicit `active_scenarios`. An
empty scenario list is appropriate only when the caller knows no scenarios are
active. Actor and scenario object lifetime remains the caller's responsibility.
It checks basic control bounds, but does not validate correction safety.

To reproduce the standalone smoke test, start a disposable CARLA 0.9.15 server
on port 31000, then from the Garage checkout run:

```bash
export PDM_ROOT=/home/casko/phd-code/Bench2DriveZoo-pdm-light
export PYTHONPATH="$PDM_ROOT:$PDM_ROOT/downloads/carla_garage/team_code:$PDM_ROOT/downloads/carla_garage/leaderboard_autopilot:$PDM_ROOT/downloads/carla_garage/scenario_runner_autopilot:/home/casko/phd-code/Carla/PythonAPI/carla"
"$PDM_ROOT/b2d_zoo-pdm-light.venv/bin/python" "$PDM_ROOT/scripts/probe_pdm_lite.py" --port 31000 --ticks 100 --revision 48e6a6dbcb133220333bd65e242fbc2b492bb15b
```

The test loads Town07, changes world settings, and creates actors. It does not
exercise Bench2Drive scenarios. On 2026-11-19, it produced valid controls for
100 steps and moved the vehicle 30.7 m. A default Town10HD_Opt test failed
because Garage ships `Town10HD_speed_limits.npy`, not a matching Opt filename;
no equivalence of those map datasets is assumed.

This does not establish scenario-provider compatibility, collision safety,
reactive traffic, or takeover of a reconstructed event. Those remain necessary
before accepting a PDM-Lite correction.

A second probe warmed the vehicle with 30 ticks of fixed throttle before
initializing the expert. With Garage's default steering noise, the adapter
rejected `steer=1.00077` (noise is added after steering computation). The
adapter now explicitly disables this noise and records the setting. Repeating
with a 6.02 m/s handoff produced valid-range controls but sustained saturated
steering and only 3.72 m displacement in 60 ticks. The fixed-throttle warm-up
is not guaranteed to follow the route; this test does **not** establish a valid
mid-route takeover. A route-following warm-up, correct remaining-route
initialization, route adherence, traffic, and scenario continuity still need
validation.

A route-following warm-up followed by a fresh expert initialized with the route
from the nearest remaining waypoint gave a more useful handoff: at 8.14 m/s,
0.19 m from that waypoint, it returned in-range controls for 60 ticks and moved
24.08 m. This was a single-vehicle test and did not measure collision safety,
route adherence over the continuation, reactive traffic or scenario continuity.
The caller must supply a suitable remaining route; the adapter does not infer it.

## Recorded closed-loop route evaluation

On 2026-11-19, the unmodified Garage `autopilot.py` was evaluated on the
Town07 `RouteScenario_24948` signalized-right-turn route using the Garage
leaderboard/scenario runner, CARLA 0.9.15, a 0.05 s synchronous step and seed 0.
The full 70.325 m route finished with 100% route completion, a 100.0 driving
score and no logged infractions. The log has one failed vehicle-spawn warning;
no assumption is made that every intended background actor spawned. It also
reports duplicate camera-destruction warnings during evaluator cleanup, after
both videos and statistics were written. This is one route, not the complete
Bench2Drive benchmark or a test of reconstructed takeover.

Outputs are in `outputs/pdm_lite_eval/town07_signalized_full_20261119/`:
`chase.mp4`, `overhead.mp4`, `results.json`, `eval.log`,
`video_metadata.json`, and the CARLA `carla_recording.log`. Each MP4 was
verified by decoding; the capture queue reported no dropped frames. Cameras
were attached independently of the expert's sensor suite and encoded at 10 fps.
The preceding `town07_signalized_20261119` run omitted `SCENARIO_RUNNER_ROOT`;
its scenario was skipped and its results are not a valid scenario evaluation.

To repeat, launch a separate CARLA server on port 31000, create an empty output
directory, then run from the Garage checkout (substitute the output path):

```bash
export PDM_ROOT=/home/casko/phd-code/Bench2DriveZoo-pdm-light
export GARAGE="$PDM_ROOT/downloads/carla_garage"
export PYTHONPATH="$PDM_ROOT:$GARAGE/team_code:$GARAGE/leaderboard_autopilot:$GARAGE/scenario_runner_autopilot:/home/casko/phd-code/Carla/PythonAPI/carla"
export SCENARIO_RUNNER_ROOT="$GARAGE/scenario_runner_autopilot"
export PDM_VIDEO_DIR="$PDM_ROOT/outputs/pdm_lite_eval/NEW_RUN"
mkdir -p "$PDM_VIDEO_DIR"
cd "$GARAGE"
DATAGEN=0 DEBUG_CHALLENGE=0 "$PDM_ROOT/b2d_zoo-pdm-light.venv/bin/python" -u \
  "$PDM_ROOT/scripts/run_pdm_recorded_evaluator.py" leaderboard_autopilot/leaderboard/leaderboard_evaluator_local.py \
  --routes="$PDM_ROOT/one_scenario_town07.xml" --repetitions=1 --track=MAP \
  --checkpoint="$PDM_VIDEO_DIR/results.json" --debug-checkpoint="$PDM_VIDEO_DIR/live_results.txt" \
  --agent=team_code/autopilot.py --agent-config=team_code --debug=0 \
  --record="$PDM_VIDEO_DIR/carla_recording" --port=31000 --traffic-manager-port=51000 \
  --traffic-manager-seed=0 --timeout=120 --resume=0
```
