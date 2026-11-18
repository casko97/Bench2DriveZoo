# Post-training with feedback for autonomous driving

## Goal and initial scope

Build a modular pipeline around Bench2Drive and CARLA that improves a pretrained VAD policy using safety-triggered expert feedback. The first implementation will:

- Detect collision, low-time-to-collision (TTC), and off-road events during closed-loop driving.
- Record a configurable window before and after each event.
- Reconstruct a common intervention point before the event and generate a correction in a separate CARLA continuation using PDM-Lite.
- Validate and store corrections and preference data.
- Fine-tune and evaluate the policy in separate, repeatable rounds.

Human annotation, delegation between feedback sources, alternative experts, and realism-based triggers are future extensions. Interfaces should allow these to be added without redesigning the pipeline. PDM-Lite is the initial expert policy, rather than an IDM-only controller; it includes IDM among other planning and control components and uses privileged simulator information.

## Working procedure

Implement the stages below one at a time. Each stage has its own tests and reviewable outcome. After presenting a completed stage and its verification results, stop so the project owner can review and commit it manually before implementation proceeds to the next stage.

## Collection and training rounds

Each round uses a fixed policy checkpoint throughout collection:

1. Run closed-loop scenarios and record triggered events.
2. Reconstruct and rerun eligible events with PDM-Lite control beginning at a validated pre-event anchor.
3. Validate corrections and create a versioned training dataset.
4. Fine-tune a new checkpoint in a separate training phase.
5. Evaluate it on held-out routes.
6. Use the resulting checkpoint as the fixed policy for the next round.

Every event, correction, dataset snapshot, and checkpoint must retain its round and model provenance. The initial strategy does not use TakeAD's shadow-mode intervention in the original simulation.

## Implementation stages

### 1. Baseline and expert feasibility audit

- Verify the local VAD checkpoint, closed-loop runner, model inputs and outputs, and training interface. Assess the availability and integration requirements of a compatible pretrained VADv2 model.
- Compare approaches for TakeAD-inspired preference training and recommend a baseline for the project owner's decision.
- Assess PDM-Lite's CARLA version, dependencies, license, route interface, and compatibility with the local Bench2Drive environment. Identify what is needed to initialize it partway through a reconstructed scenario.

**Acceptance:** a reproducible baseline run and reviewed recommendations for the policy and expert integration. Choose the training implementation after the policy audit.

### 2. Data contracts and storage

- Define versioned interfaces for runs, simulator frames, triggers, feedback providers, intervention anchors, corrections, preference examples, and training rounds.
- Use a lightweight metadata database with references to files containing images and larger arrays.
- Track timestamps, coordinate frames, checkpoint identity, route and scenario configuration, expert provenance, status, validation results, and rejection reasons.

**Acceptance:** synthetic round-trip tests covering valid, incomplete, and interrupted records.

### 3. Safety trigger monitoring

- Implement interchangeable detectors for collisions, low TTC, and off-road events.
- Reuse existing CARLA or ScenarioRunner collision and off-road criteria where suitable. Evaluate existing TTC-related calculations and wrap or extend them for the VAD monitoring loop.
- Make thresholds, event deduplication, and cooldown configurable; retain the evidence that caused each trigger.

**Acceptance:** synthetic tests for all three trigger types and a short CARLA run verifying detection and timing.

### 4. Event-window and anchor recording

- Maintain a bounded rolling buffer before each trigger and record a configurable period afterward.
- Save synchronized policy inputs and outputs, ego and nearby actor states, route context, traffic-light state, and simulator configuration.
- Select and record candidate intervention anchors before the trigger, including the observation history required by the chosen model.
- Write asynchronously with bounded queues and mark dropped or incomplete windows explicitly.

**Acceptance:** synchronization and buffer tests, plus a short closed-loop run with measured collection overhead.

### 5. Common-start reconstruction and takeover feasibility

- Test CARLA recorder playback up to a recorded anchor, including additional recorder data where supported. Compare playback with a seeded scenario rerun and targeted restoration of ego and relevant actor state.
- At the anchor, measure ego position, orientation, linear and angular velocity, nearby actor states, and traffic-light differences against the original recording.
- Test whether control can be transferred to PDM-Lite while relevant traffic and Bench2Drive scenario behavior continue appropriately. Assess a cheap feasibility pre-check for candidate anchors before scheduling full CARLA reruns.

**Acceptance:** a documented and tested reconstruction method for representative scenarios, with measured mismatch and explicit acceptance tolerances. If recorder playback cannot resume the scenario reliably, use the best validated seeded-rerun approach and retain state-matching checks.

### 6. PDM-Lite expert and correction validation

- Integrate PDM-Lite behind the feedback-provider interface and initialize it at the validated intervention anchor. Record its privileged simulator inputs and configuration.
- Continue the CARLA simulation under expert control so surrounding actors can respond. Preserve the original and corrected continuations separately.
- Validate collisions, vehicle feasibility, progress, and route adherence. Mark unsupported or unsafe corrections as rejected.

**Acceptance:** isolated integration tests and visually inspected CARLA expert continuations, including rejected corrections.

### 7. Preference-data construction

- Use the recorded anchor observation as the common context. Align the VAD candidate and accepted expert correction to the chosen model's trajectory horizon and coordinate convention.
- Preserve original and rerun trajectories separately, together with measured starting-state mismatch and provenance.
- Reject examples with inadequate alignment, insufficient observation history, invalid corrections, or trajectories the model cannot represent.

**Acceptance:** alignment and validation tests, plus visual inspection of accepted and rejected examples.

### 8. Separate batch fine-tuning

- Freeze a validated dataset snapshot and implement a TakeAD-inspired preference objective suited to the baseline selected in stage 1.
- If the existing deterministic VAD is selected, first review the scoring or probabilistic adaptation required for a meaningful preference objective.
- Keep corrective imitation independently selectable so it can be tested alongside preference optimization. Save each checkpoint with its configuration and dataset provenance.

**Acceptance:** dataset-loading and gradient tests, checkpoint save/reload, and a small overfit test showing the intended preference change.

### 9. Round orchestration and evaluation

- Connect collection, reconstruction, correction, data preparation, training, and evaluation as separate commands with explicit round boundaries.
- Start with one simulator worker. Use fixed-step synchronous simulation and isolated worker ports, output paths, and seeds. Preserve camera rendering where the selected policy or validation needs it.
- Measure collection and rerun throughput, storage, reconstruction success, queue behavior, and accepted corrections per simulator hour before scaling.
- Compare baseline and updated checkpoints on held-out routes using Bench2Drive driving score, success, and infractions, alongside trigger counts, accepted corrections, and performance versus feedback queries.

**Acceptance:** a complete smoke-test round producing a traceable event, validated correction, training snapshot, reloadable checkpoint, and baseline comparison. The same workflow can then start another round with the updated checkpoint.

## Assumptions and limitations

- A common anchor can substantially improve comparability, but CARLA recorder playback and actor-state restoration are not guaranteed to restore every internal simulator, scenario, or controller state. Acceptance depends on the stage 5 feasibility test and measured mismatch.
- PDM-Lite is a privileged expert and may not provide a valid correction for every event. Corrections require validation, and its simulator-only information must be recorded.
- TakeAD uses separate collection, imitation, and preference-optimization phases across repeated rounds. Our separate CARLA reruns and PDM-Lite corrections are an adaptation of that approach.
- The initial pipeline establishes whether corrections can be collected, aligned, and used for training. Safety and human-like realism improvements must be demonstrated through evaluation.

## References

- [TakeAD](https://arxiv.org/abs/2512.17370)
- [RoG-DAgger](https://arxiv.org/abs/2608.24525)
- [PDM-Lite in CARLA Garage](https://github.com/autonomousvision/carla_garage/tree/leaderboard_2)
- [CARLA recorder](https://carla.readthedocs.io/en/0.9.12/adv_recorder/)
