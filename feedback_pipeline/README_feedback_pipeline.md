# Feedback data contracts and storage

This package defines records for collection and training rounds, simulator frames, triggers, event windows, intervention anchors, reruns, expert corrections, preferences, and dataset manifests. 

`FeedbackProvider` is an interface for future expert adapters; this component does not run an expert or collect data.

## Record formats

Every record has a caller-assigned `id`, a `schema_version`, a `status` (`pending`, `complete`, `rejected`, or `failed`), an optional `reason`, a `metadata` dictionary, and a dictionary of named `artifacts`. Rejected and failed records require a reason. The version 1 component-specific fields are:

| Record | Fields | Purpose |
| --- | --- | --- |
| `TrainingRound` | `policy_checkpoint`, `configuration` | Identifies a round's fixed collection policy and configuration. |
| `CollectionRun` | `round_id`, `route`, `scenario`, `simulator`, `seeds` | Describes a simulator run and its provenance. |
| `Frame` | `run_id`, `frame_number`, `simulation_time_seconds`, `coordinate_frames`, `ego_state`, `actor_states`, `traffic_lights`, `policy_context` | Records a time-stamped state from the original collection run. |
| `Trigger` | `run_id`, `frame_id`, `trigger_type`, `evidence` | Identifies an event and why it was triggered. |
| `EventWindow` | `trigger_id`, `frame_ids`, requested and actual durations before and after | Groups the original run's recorded frames around an event. |
| `Anchor` | `trigger_id`, `frame_id`, `observation_history` | Identifies the pre-event intervention frame and preceding model context. |
| `Rerun` | `anchor_id`, `simulator`, `seeds`, `state_match` | Identifies a separate continuation and records its starting-state comparison. |
| `Correction` | `rerun_id`, `provider`, `coordinate_frames`, `validation` | Records expert provenance and validation for a correction. |
| `Preference` | `anchor_id`, `correction_id`, `coordinate_frames`, `validation` | Links a preference example to the anchor and correction. |
| `DatasetSnapshot` | `round_id`, `preference_ids`, `configuration` | Lists preference records selected for a training dataset. |

Record references link the flow `TrainingRound → CollectionRun → Frame/Trigger → EventWindow/Anchor → Rerun → Correction → Preference`; a dataset manifest references the round and selected preferences. An event window references frames, rather than belonging to an anchor. The store checks reference types, run consistency for trigger, window and anchor frames, and that a preference and its correction refer to the same anchor.

## Original and corrected driving data

The storage is flexible about what can be attached. A producer can put structured, JSON-compatible values such as vehicle positions in `Frame.ego_state` and `Frame.actor_states`, and attach arbitrary named binary artifacts such as camera images, video chunks, arrays, or planned trajectories to a record. Artifact names, file formats, coordinate conventions, units, sampling rates, and the contents of the flexible dictionaries are **not yet fixed**. A producer must specify those details; the store does not interpret the bytes or synchronize streams. Artifact reads and writes currently load the complete blob into memory.

The intended representation for an event is:

- **Original executed trajectory:** the original `CollectionRun` has time-stamped `Frame` records. Their ego states, ordered using `frame_number` or `simulation_time_seconds`, can represent where VAD actually drove. The `EventWindow` identifies frames around the trigger, including the original continuation after the anchor when those frames were captured. Camera images and other sensor data can be attached to the corresponding frames.
- **Original planned trajectory:** the VAD prediction at the anchor can be attached to the anchor's `Frame` as an artifact, for example under `vad_planned_trajectory`. This is the trajectory VAD predicted, which is distinct from the trajectory the vehicle subsequently executed. Its exact encoding and artifact name will be defined during collection and preference-data implementation.
- **Expert correction:** the `Correction` links to a `Rerun`, which links to the same `Anchor`. A producer can attach the expert trajectory to the correction as an artifact, for example under `expert_executed_trajectory`. The rerun's `state_match` records whether the reconstructed start was sufficiently similar.
- **Preference example:** a `Preference` links the anchor and correction and can also carry artifacts for the aligned preferred and dispreferred candidates. The store currently does not require or automatically construct those candidates, choose between planned and executed VAD trajectories, or establish their alignment.

These are supported data placements, not data already collected by this package. Later stages must implement collection, choose and document the trajectory representation, and verify that the candidates share the intended observation, start time, coordinate frame, and horizon. A captured window can be incomplete, and its original executed continuation need not cover the full training horizon. The anchor also references observation-history frames, but this contract does not yet guarantee restoration of VAD's temporal BEV state or prior controls.

## Using the store

```python
from feedback_pipeline import CollectionRun, FeedbackStore, Frame, TrainingRound

with FeedbackStore('outputs/feedback/example') as store:
    image = store.put_artifact(b'example-image-bytes', media_type='image/png')
    store.save(
        TrainingRound('round-1', policy_checkpoint={'path': 'model.pth', 'sha256': '...'}),
        CollectionRun('run-1', round_id='round-1', route={'id': 'route-1'},
                      simulator={'version': '0.9.15'}, seeds={'traffic_manager': 0}),
        Frame('frame-1', run_id='run-1', frame_number=10, simulation_time_seconds=0.5,
              coordinate_frames={'ego_state': 'CARLA world'}, artifacts={'front_camera': image}),
    )
    assert store.read_artifact(store.get('frame-1').artifacts['front_camera']) == b'example-image-bytes'
```

* *Record IDs* are caller-assigned and unique across record types. 
* `save` accepts a batch in any order, checks reference types and relevant run/anchor consistency, and commits its metadata atomically. * Existing records may be updated, but their type and record references cannot change. 
* `pending` represents incomplete work; 
* `rejected` and `failed` records require a reason. 
* Correction and state-match validations carry separate status, reasons, and measurements. 
* Producers must explicitly provide coordinate-frame conventions, timestamps, seeds, checkpoint identity, and expert configuration as these become available; the package does not infer or validate physical units, trajectory alignment, or policy safety.

* `put_artifact` publishes content-addressed blobs before their metadata references are saved. 
    * It writes through a temporary file and atomically renames it after flushing. 
    * If a record transaction fails or a process is interrupted, an unreferenced blob or temporary file may remain; a partial metadata batch is not published. 
    * Readers verify size and SHA-256 by default, raising `IntegrityError` for missing or damaged data. 
    * `get(..., verify_artifacts=False)` can inspect metadata when a blob is unavailable. 
    * Artifact publication and reading currently use in-memory bytes; streaming and garbage collection are future work.

* `DatasetSnapshot` currently records a manifest of preference IDs and configuration. 
    * It does **not** freeze the contents or validation status of referenced records; a truly immutable training snapshot and eligibility checks belong to the training-data stage. 
    * Similarly, record status and validation status are independent: this store does not automatically treat an accepted correction as safe or eligible for training.

* Each `FeedbackStore` instance owns one SQLite connection; use separate instances for separate threads or processes. 
    * SQLite transactions serialize metadata writes. The database's `user_version` and each record's `schema_version` are checked on open/read; unknown versions are rejected. No migration is implemented yet.

Run the component tests from the repository root:

```bash
./b2d_zoo.venv/bin/python -m pytest -q tests/test_feedback_store.py
```
