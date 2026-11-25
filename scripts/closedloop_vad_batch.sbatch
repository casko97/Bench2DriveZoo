#!/usr/bin/env bash
#SBATCH --job-name=vad-closed-batch
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:2
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH --constraint=arwen
#SBATCH --output=vad-batch-%A_%a.out
#SBATCH --error=vad-batch-%A_%a.err

# Submit through submit_closedloop_vad_batches.sh or specify --array explicitly.
set -euo pipefail
repo_dir=${SLURM_SUBMIT_DIR:-$PWD}
batch_index=${SLURM_ARRAY_TASK_ID:?Submit as a Slurm array with --array}
batch_size=${BATCH_SIZE:-5}
bench_root=${BENCH2DRIVE_ROOT:-$HOME/Bench2Drive}
source_routes=${BATCH_ROUTES:-$bench_root/leaderboard/data/bench2drive_0.0.4_val.xml}
[[ "$source_routes" = /* ]] || source_routes="$bench_root/$source_routes"
[[ -f "$source_routes" ]] || { echo "Missing routes XML: $source_routes" >&2; exit 1; }
# Every retry has a distinct directory and a copy of the exact selected routes.
run_stamp=$(date +%Y%m%d_%H%M%S_%N)
queue_dir=${BATCH_QUEUE_DIR:-"$repo_dir/outputs/closed_loop/batch_queue_array_${SLURM_ARRAY_JOB_ID:-manual}"}
export SAVE_PATH="$queue_dir/batch_${batch_index}/attempt_${SLURM_JOB_ID:-manual}_${run_stamp}"
mkdir -p "$SAVE_PATH"
selected_routes="$SAVE_PATH/routes.xml"
selector_args=()
case "${BATCH_GROUP_BY_TOWN:-0}" in
    0) ;;
    1) selector_args+=(--group-by-town) ;;
    *) echo 'BATCH_GROUP_BY_TOWN must be 0 or 1' >&2; exit 2 ;;
esac
python3 "$repo_dir/scripts/select_closed_loop_batch.py" "$source_routes" --batch-size "$batch_size" "${selector_args[@]}" --index "$batch_index" --output "$selected_routes"
# Use a fresh checkpoint for every attempt, rather than inheriting one from a
# different batch or a previous full-suite run.
unset CHECKPOINT_ENDPOINT CARLA_VULKAN_ADAPTER
export OUTPUT_ROOT="$SAVE_PATH"
export ROUTES="$selected_routes"
export CLOSED_LOOP_SCENARIOS=all
# Hold a cooperative node-local lock until this task and its launcher exit.
source "$repo_dir/scripts/reserve_batch_ports.sh"
printf 'Array job %s, batch %s: %s\n' "${SLURM_ARRAY_JOB_ID:-unknown}" "$batch_index" "$source_routes"
bash "$repo_dir/scripts/closedloop_vad_one_scenario.sbatch"
