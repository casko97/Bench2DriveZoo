#!/usr/bin/env bash
# Submit from the repository root; BATCH_SIZE and MAX_CONCURRENT are optional.
set -euo pipefail
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
[[ "$PWD" -ef "$repo_dir" ]] || { echo 'Submit from the Bench2DriveZoo repository root.' >&2; exit 1; }
bench_root=${BENCH2DRIVE_ROOT:-$HOME/Bench2Drive}
source_routes=${BATCH_ROUTES:-$bench_root/leaderboard/data/bench2drive_0.0.4_val.xml}
[[ "$source_routes" = /* ]] || source_routes="$bench_root/$source_routes"
batch_size=${BATCH_SIZE:-5}
max_concurrent=${MAX_CONCURRENT:-1}
[[ "$max_concurrent" =~ ^[1-9][0-9]*$ ]] || { echo 'MAX_CONCURRENT must be a positive integer' >&2; exit 2; }
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
export BATCH_ROUTES="$source_routes" BATCH_SIZE="$batch_size" BATCH_QUEUE_DIR="$queue_dir"
printf 'Queue artifacts: %s\n' "$queue_dir"
printf 'Submitting %s batches of up to %s routes, at most %s at a time.\n' "$batch_count" "$batch_size" "$max_concurrent"
sbatch --array="0-$((batch_count - 1))%${max_concurrent}" \
    --output="$queue_dir/slurm-%A_%a.out" --error="$queue_dir/slurm-%A_%a.err" \
    "$@" scripts/closedloop_vad_batch.sbatch
