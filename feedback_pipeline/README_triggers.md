# Triggers

## Collision and off-road trigger monitoring

The feedback pipeline has its own closed-loop launcher. It emits trigger events by default without changing vehicle control or route stopping behavior. The standard and feedback launchers share `scripts/closed_loop_common.sh` and `scripts/closed_loop_evaluator.py`; only the feedback entry point enables feedback hooks:

```bash
./scripts/run_feedback_closed_loop_vad_v004.sh --one-scenario
```

Events are appended to `feedback_triggers.jsonl` in the run's artifact directory. Each contains `type`, benchmark `frame`, simulator `simulation_time_seconds`, route index/repetition, and source-specific `evidence`. 

Collision triggers use only benchmark events (callbacks filtered out by the benchmark do not trigger):
* `COLLISION_STATIC`
* `COLLISION_VEHICLE`
* `COLLISION_PEDESTRIAN`
* `OUTSIDE_ROUTE_LANES_INFRACTION` *(outside-lane or wrong-direction driving)*

For collisions, `frame` is the benchmark event's frame and `simulation_time_seconds` is the current world snapshot time when the event is processed. Since collision callbacks are asynchronous, those values can refer to different simulation ticks. Preserve both and resolve alignment explicitly during event-window collection.

Configure each trigger reason in [`trigger_config.json`](trigger_config.json), loaded when the evaluator starts:

```json
{
  "collision": {"mode": "multiple", "cooldown_seconds": 2.0},
  "outside_route_lanes_infraction": {"mode": "once", "cooldown_seconds": 2.0}
}
```

| Field | Default | Meaning | Benchmark limitations and impact |
| --- | --- | --- | --- |
| `collision.mode` | `multiple` | `once` emits at most one collision trigger per route; `multiple` permits more. Static, vehicle and pedestrian collisions share this policy. | Bench2Drive filters collisions using conditions including proximity and ego speed; filtered contacts cannot trigger. The launcher stops after the first accepted collision by default, so observing later collisions also requires `SUSTAINED_COLLISION_FRAMES=0`. This changes the launcher's early stop, not the benchmark criteria. |
| `collision.cooldown_seconds` | `2` | Non-negative finite simulation-time cooldown per other actor in multiple mode. | Even at `0`, only benchmark-accepted collisions can trigger; the benchmark's own filtering still applies. |
| `outside_route_lanes_infraction.mode` | `once` | `once` emits the first populated lane event update; `multiple` permits later updates. | Bench2Drive maintains one cumulative event per route. Multiple triggers are updates to that event, **not necessarily separate departures**, and updates may continue after returning to the lane. The update frame may be later than the actual departure; distinct departures cannot be reliably inferred from this event alone. |
| `outside_route_lanes_infraction.cooldown_seconds` | `2` | Non-negative finite simulation-time cooldown between lane-event updates in multiple mode. | A cooldown of `0` can emit every populated update to the cumulative event, including updates that are not new departures. |

A cooldown of `0` disables our additional suppression. Cooldown has no practical effect after the first event in `once` mode. Policies reset between routes and repetitions. Both reasons and their two fields are required; unknown fields, invalid modes, and negative or non-finite cooldowns are rejected. Previous per-reason cooldown and mode environment variables are no longer read.

Example:

```bash
FEEDBACK_TRIGGER_CONFIG=/path/to/my-trigger-config.json \
  ./scripts/run_feedback_closed_loop_vad_v004.sh --one-scenario
```

`FEEDBACK_TRIGGER_CONFIG` is optional; it selects an alternative file rather than overriding individual fields. A relative path is resolved from the directory where the launcher is invoked. Monitoring defaults to enabled in the feedback launcher; set `FEEDBACK_TRIGGERS=0` to disable it. Output defaults to `outputs/feedback_closed_loop`, separate from the default evaluation launcher.

These JSONL records are the stage 3 monitoring output; integration with the SQLite record store and capture of synchronized event windows are future stages. Events can arrive after the matching frame's agent tick, so consumers must use the recorded benchmark frame rather than assume log order is frame order.
