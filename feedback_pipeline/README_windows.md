# Event-window recording

The feedback launcher records data around accepted benchmark triggers. Recording is enabled by default when feedback triggers are enabled and currently supports `VadAgent` only. It does not change the standard evaluation launcher or vehicle control.

```bash
./scripts/run_feedback_closed_loop_vad_v004.sh --one-scenario
```

## Configuration

Edit [`window_config.json`](window_config.json) to set the window duration, recording limits, and data saved per frame:

| Field | Default | Meaning |
| --- | --- | --- |
| `before_seconds`, `after_seconds` | `1.0`, `1.0` | Duration before and after the benchmark trigger frame. Both may be zero. |
| `max_buffer_mib` | `256` | Limit for the compressed rolling history and pending windows. |
| `writer_queue_frames` | `2` | Maximum number of frames waiting for the background writer. |
| `max_pending_events` | `4` | Maximum number of windows awaiting completion. |
| `actor_radius_m` | `60.0` | Radius around the ego vehicle for actor and traffic-light state. |
| `record.cameras` | All seven cameras | Select any of `CAM_FRONT`, `CAM_FRONT_LEFT`, `CAM_FRONT_RIGHT`, `CAM_BACK`, `CAM_BACK_LEFT`, `CAM_BACK_RIGHT`, and `bev`. The latter is CARLA's overhead RGB camera. |
| `record.sensors` | `GPS`, `IMU`, `SPEED` | Select which sensor values to save. |
| `record.ego_state`, `record.actor_states`, `record.traffic_lights` | `true` | Save ego state, nearby actor states, and traffic-light states, respectively. |
| `record.policy_outputs`, `record.previous_controls` | `true` | Save the agent's policy metadata and previous controls, respectively. |

Use empty lists or `false` to omit data. All fields are required; invalid values and unknown names are rejected. Selection affects event-window recording only, not VAD inputs or benchmark behavior. Omitting data can make a window unsuitable for training or reconstruction.

To use a separate configuration file:

```bash
FEEDBACK_WINDOW_CONFIG=/path/to/my-window-config.json \
  ./scripts/run_feedback_closed_loop_vad_v004.sh --one-scenario
```

Relative config paths are resolved from the launcher's invocation directory. Set `FEEDBACK_CAPTURE_WINDOWS=0` to disable recording, or `FEEDBACK_ROUND_ID` to specify the shared round ID; otherwise the launch run ID is used.

## Output and limitations

Each run saves records to `feedback_data/feedback.sqlite3` and camera PNGs to `feedback_data/blobs/` inside the run directory. Records include the round and checkpoint identity, scenario, trigger, window, frames, and a candidate pre-trigger anchor. Camera PNGs preserve the original four CARLA image channels. The anchor is the captured pre-trigger frame closest to the midpoint of the requested pre-trigger interval; it is not yet verified for replay.

The background writer drops frames when its queue is full. A window is marked `failed` if its coverage is insufficient, simulation frames or selected sensor data are missing, or selected sensors are out of sync. Failed windows remain inspectable. Drop counts are reported at shutdown and included in window metadata. Pending windows are flushed on graceful shutdown; a crash or forced stop can leave a partial run.

Collision events may be processed later than their benchmark frame; windows match the recorded frame, not callback time. The launcher stops at the first accepted collision by default, which can prevent post-trigger capture. Set `SUSTAINED_COLLISION_FRAMES=0` to disable that early stop, subject to other benchmark termination conditions.

The overhead camera is distinct from VAD's internal temporal BEV state, which is **not** recorded. Exact policy replay and simulator-state reconstruction remain unverified; this stage does not generate or validate expert corrections.
