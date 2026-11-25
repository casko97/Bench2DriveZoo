# Town-grouped closed-loop evaluation

From the repository root, submit a separate Slurm array:

```bash
bash scripts/submit_closedloop_vad_by_town.sh
```

This variant groups routes by their `town` in first-seen town order, preserves source order within each town, and takes up to five routes per batch. For the standard 220-route v0.0.4 XML it creates 50 batches; partially filled batches are never combined across towns. As with the regular batched launcher, one batch runs at a time by default, each task requests two GPUs, eight CPUs, 32 GB RAM and four hours, and the submission prints a separate output folder for the queue. `BATCH_SIZE`, `MAX_CONCURRENT`, `BATCH_ROUTES`, and `sbatch` options work as in [closed_loop_batches.md](closed_loop_batches.md).

Each batch starts a new CARLA process. **The evaluator reloads the CARLA world before every route**, even when consecutive routes are in the same town; town grouping alone does not eliminate map reloads.

To run or retry only town-grouped batch 3 against the same unchanged source XML:

```bash
BATCH_GROUP_BY_TOWN=1 sbatch --array=3 scripts/closedloop_vad_batch.sbatch
```

The group-based indices are different from the regular consecutive-route batch indices. Each retry starts a fresh CARLA server and gets its own output directory and checkpoint. For an exact replay if the source XML may have changed, point `BATCH_ROUTES` at a saved attempt's `routes.xml` and submit `--array=0` with the same batch size. Route outcomes still need to be inspected separately from Slurm task status.
