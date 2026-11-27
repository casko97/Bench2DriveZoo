#!/usr/bin/env bash
# Submit from the repository root; BATCH_SIZE and MAX_CONCURRENT are optional.
set -euo pipefail
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ "$PWD" -ef "$repo_dir" ]] || { echo 'Submit from the Bench2DriveZoo repository root.' >&2; exit 1; }
bench_root=${BENCH2DRIVE_ROOT:-$HOME/Bench2Drive}
source_routes=${BATCH_ROUTES:-$bench_root/leaderboard/data/bench2drive_0.0.4_val.xml}
printf 'Using route XML: %s\n' "$source_routes"
[[ "$source_routes" = /* ]] || source_routes="$bench_root/$source_routes"
batch_size=${BATCH_SIZE:-5}
max_concurrent=${MAX_CONCURRENT:-0}
[[ "$max_concurrent" =~ ^(0|[1-9][0-9]*)$ ]] || { echo 'MAX_CONCURRENT must be 0 (unlimited) or a positive integer' >&2; exit 2; }
selector_args=()
case "${BATCH_GROUP_BY_TOWN:-0}" in
    0) ;;
    1) selector_args+=(--group-by-town) ;;
    *) echo 'BATCH_GROUP_BY_TOWN must be 0 or 1' >&2; exit 2 ;;
esac
batch_count=$(python3 "$repo_dir/scripts/select_closed_loop_batch.py" "$source_routes" --batch-size "$batch_size" "${selector_args[@]}" --count)
queue_root="$repo_dir/outputs/closed_loop"
mkdir -p "$queue_root"
queue_dir=$(mktemp -d "$queue_root/batch_queue_$(date +%Y%m%d_%H%M%S)_XXXXXX")
export BENCH2DRIVE_ROOT="$bench_root"
export BATCH_ROUTES="$source_routes" BATCH_SIZE="$batch_size" BATCH_QUEUE_DIR="$queue_dir"
printf 'Queue artifacts: %s\n' "$queue_dir"
array_spec="0-$((batch_count - 1))"
if ((max_concurrent > 0)); then
    array_spec+="%${max_concurrent}"
    printf 'Submitting %s batches of up to %s routes, at most %s at a time.\n' "$batch_count" "$batch_size" "$max_concurrent"
else
    printf 'Submitting %s batches of up to %s routes; Slurm controls parallelism.\n' "$batch_count" "$batch_size"
fi
array_submit_output=$(sbatch --array="$array_spec" \
    --output="$queue_dir/slurm-%A_%a.out" --error="$queue_dir/slurm-%A_%a.err" \
    "$@" scripts/closedloop_vad_batch.sbatch)
printf '%s\n' "$array_submit_output"
array_job_id=${array_submit_output##* }
if [[ "${ENABLE_BATCH_AGGREGATION:-1}" == 1 && "$array_job_id" =~ ^[0-9]+$ ]]; then
    aggregate_submit_output=$(sbatch --dependency="afterany:${array_job_id}" \
        --export="ALL,BATCH_QUEUE_DIR=${queue_dir}" \
        scripts/aggregate_closedloop_batches.sbatch)
    printf 'Aggregation job (runs after array %s): %s\n' "$array_job_id" "$aggregate_submit_output"
elif [[ "${ENABLE_BATCH_AGGREGATION:-1}" != 0 ]]; then
    printf 'Could not parse array job ID; submit aggregation manually for %s.\n' "$queue_dir" >&2
fi
