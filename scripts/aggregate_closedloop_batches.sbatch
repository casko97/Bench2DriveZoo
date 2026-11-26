#!/usr/bin/env bash
# Aggregate a completed or partially completed batch queue after its array ends.
#SBATCH --job-name=vad-closed-aggregate
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:15:00
#SBATCH --constraint=arwen
#SBATCH --output=aggregate-%j.out
#SBATCH --error=aggregate-%j.err

set -euo pipefail
repo_dir=${REPO_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}
conda_base=${CONDA_BASE:-/Midgard/home/casko/miniforge3}
conda_env=${CONDA_ENV:-b2d_zoo.venv}
queue_dir=${BATCH_QUEUE_DIR:?BATCH_QUEUE_DIR must identify the batch queue}
bench_root=${BENCH2DRIVE_ROOT:?Set BENCH2DRIVE_ROOT to the Bench2Drive checkout}
[[ -f "$conda_base/etc/profile.d/conda.sh" ]] || { echo 'Conda initialization not found' >&2; exit 1; }
set +u
source "$conda_base/etc/profile.d/conda.sh"
conda activate "$conda_env"
set -u
python "$repo_dir/scripts/aggregate_closedloop_batches.py" "$queue_dir" --bench2drive-root "$bench_root"
