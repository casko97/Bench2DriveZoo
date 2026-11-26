# Batched closed-loop VAD evaluation

Submit from the Bench2DriveZoo repository root:

```bash
bash scripts/submit_closedloop_vad_batches.sh
```

The script creates a Slurm array with one task for each consecutive group of five routes in the source XML, with Slurm scheduling as many tasks concurrently as resources and cluster policies allow. For the default 220-route v0.0.4 suite this produces batches 0–43. Each task starts its own CARLA server, reloads the world before every route, evaluates its routes in order, and requests two GPUs, 8 CPUs, 32 GB RAM and four hours. These are starting estimates; use `--time=...` as an argument to the submission script if needed. CARLA GPU selection, Conda activation, image saving and GIF creation use the existing cluster launcher.

Inspect the array with `squeue -u "$USER"` and its task states with `sacct -j ARRAY_JOB_ID --format=JobID,JobName,State,ExitCode,Elapsed`. The submission command prints the new queue directory; Slurm logs are `slurm-ARRAY_JOB_ID_TASK_ID.out` and `.err` inside that directory. The task output lists the selected route IDs. Individual scenario failures are benchmark outcomes and may not make a Slurm task fail; inspect each checkpoint and `run.log` for route-level results. A task can also fail during simulator setup or hit its time limit.

The submission also creates a dependent aggregation job. It runs after the array reaches a terminal state, merges the newest attempt from each batch, writes `aggregate.json`, and produces `aggregate_report.txt` with global metrics and every route's status. If any batch is missing or has unfinished records, the report is still written and the aggregation job exits nonzero so incomplete coverage is visible. Set `ENABLE_BATCH_AGGREGATION=0` to disable the dependent job.

Each attempt has a separate folder under:

```text
outputs/closed_loop/batch_queue_TIMESTAMP_UNIQUE/batch_INDEX/attempt_JOB_ID_TIMESTAMP/
```

That directory contains `routes.xml` (the exact selected routes), a fresh evaluation checkpoint JSON, `cluster.log`, `run.log`, telemetry and saved views. GIFs are created after the evaluator returns successfully. If the evaluator crashes or reaches the time limit, you can create GIFs from any saved PNG frames later with `python scripts/create_rollout_gifs.py PATH_TO_ATTEMPT`.

To rerun batch 3 from the same unchanged source XML and batch size, submit a fresh one-task array:

```bash
sbatch --array=3 scripts/closedloop_vad_batch.sbatch
```

Direct `sbatch` submissions create their own `outputs/closed_loop/batch_queue_array_ARRAY_JOB_ID/` directory; their Slurm stdout and stderr remain in the submission directory unless overridden with `sbatch` options. Each retry creates a new attempt directory and starts the five routes again; it does not overwrite or resume the previous checkpoint. If the source XML might have changed, rerun the archived route selection exactly instead, using array index 0:

```bash
BATCH_ROUTES="$PWD/outputs/closed_loop/batch_queue_TIMESTAMP_UNIQUE/batch_3/attempt_JOB_ID_TIMESTAMP/routes.xml" \
  sbatch --array=0 scripts/closedloop_vad_batch.sbatch
```

This is a fresh run of the archived routes, labeled batch 0 in the new array. Set `BATCH_SIZE` to the size used for the original attempt when it differs from five. Inspect the new task's printed route IDs to verify the selection.

Optional submission settings include `BATCH_SIZE` (default 5), `MAX_CONCURRENT` (unset or 0 means no array concurrency cap), and `BATCH_ROUTES` (an absolute XML path, or a path relative to `BENCH2DRIVE_ROOT`). For example, `MAX_CONCURRENT=2 bash scripts/submit_closedloop_vad_batches.sh` caps the array at two simultaneous tasks and can use four GPUs. Each task requests two GPUs on one node, 8 CPUs and 32 GB RAM; Slurm starts each task only when its complete allocation is available. Without a cap, a 44-task array could use up to 88 GPUs if the scheduler and cluster resources permit. Tasks on the same node reserve distinct CARLA and Traffic Manager port slots with a cooperative per-user lock; unrelated processes do not participate in this lock. The source XML and these settings must remain consistent when rerunning a batch by its original index. Batch checkpoints are independent; they are not merged into a single full-suite checkpoint.

For an already finished queue, run the posthoc aggregation directly:

```bash
python scripts/aggregate_closedloop_batches.py \
  outputs/closed_loop/batch_queue_TIMESTAMP_UNIQUE \
  --bench2drive-root "$BENCH2DRIVE_ROOT"
```
