#!/usr/bin/env bash
#SBATCH --job-name=vad-closed-smoke
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --gres=gpu:2
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --constraint=arwen
#SBATCH --output=vad-closed-%j.out
#SBATCH --error=vad-closed-%j.err

set -euo pipefail
CONDA_BASE=${CONDA_BASE:-/Midgard/home/casko/miniforge3}
CONDA_ENV=${CONDA_ENV:-b2d_zoo.venv}
[[ -f $CONDA_BASE/etc/profile.d/conda.sh ]] || { echo 'Conda initialization not found' >&2; exit 1; }
# Conda activation loads environment-specific variables such as REPO_DIR and
# BENCH2DRIVE_ROOT. Activation hooks may reference unset shell variables.
set +u
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"
set -u
REPO_DIR=${REPO_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}
REPO_DIR=$(cd "$REPO_DIR" && pwd)
run_stamp=$(date +%Y%m%d_%H%M%S_%N)
export SAVE_PATH=${SAVE_PATH:-"$REPO_DIR/outputs/closed_loop/cluster_${SLURM_JOB_ID:-manual}_${run_stamp}"}
mkdir -p "$SAVE_PATH"
exec > >(tee -a "$SAVE_PATH/cluster.log") 2>&1
printf 'Cluster log and run artifacts: %s\n' "$SAVE_PATH"
printf 'Activated Conda environment: %s\n' "$CONDA_PREFIX"
BENCH2DRIVE_ROOT=${BENCH2DRIVE_ROOT:?Set BENCH2DRIVE_ROOT to the Bench2Drive checkout}
CARLA_ROOT=${CARLA_ROOT:-/Midgard/home/casko/carla}
CHECKPOINT=${CHECKPOINT:-/local_storage/users/casko/cpts/vad_b2d_base.pth}
[[ -n ${SLURM_JOB_ID:-} && -n ${CUDA_VISIBLE_DEVICES:-} ]] || { echo 'Run inside a Slurm GPU allocation with CUDA_VISIBLE_DEVICES set' >&2; exit 1; }
IFS=, read -r -a allocated_gpus <<< "$CUDA_VISIBLE_DEVICES"
(( ${#allocated_gpus[@]} == 2 )) || { echo "Expected exactly two allocated CUDA devices; got $CUDA_VISIBLE_DEVICES" >&2; exit 1; }
[[ ${allocated_gpus[0]} != "${allocated_gpus[1]}" ]] || { echo 'Allocated CUDA devices must be distinct' >&2; exit 1; }
[[ -f $CHECKPOINT ]] || { echo "Missing checkpoint: $CHECKPOINT" >&2; exit 1; }
[[ -e $BENCH2DRIVE_ROOT/Bench2DriveZoo && $REPO_DIR -ef $BENCH2DRIVE_ROOT/Bench2DriveZoo ]] || { echo 'Bench2Drive/Bench2DriveZoo must point to this repository' >&2; exit 1; }
# Resolve CUDA ordinal 0 to a Vulkan index by PCI address; CUDA, NVML and
# Vulkan ordinal numbering may differ. The probe fails closed on ambiguity.
CARLA_VULKAN_ADAPTER=$(python "$REPO_DIR/scripts/select_carla_gpu.py")
export BENCH2DRIVE_ROOT CARLA_ROOT
export B2D_ZOO_VENV="$CONDA_PREFIX"
export SKIP_VENV_ACTIVATION=1
export MODEL_CUDA_DEVICE="${allocated_gpus[1]}"
export GPU_RANK="$CARLA_VULKAN_ADAPTER"
export TEAM_AGENT="$REPO_DIR/team_code/vad_b2d_agent.py"
export TEAM_CONFIG="$REPO_DIR/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py+$CHECKPOINT"
export SAVE_VIEWS=${SAVE_VIEWS-rgb_front,bev}
# Remove the upstream evaluator's host-wide graphicsadapter-based kill: it can
# kill other jobs. The existing supervisor tracks and cleans up descendants.
evaluator="$BENCH2DRIVE_ROOT/leaderboard/leaderboard/leaderboard_evaluator.py"
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/vad-evaluator.XXXXXX")
trap 'rm -rf "$tmp_dir"' EXIT
export EVALUATOR_PATH="$tmp_dir/leaderboard_evaluator.py"
python - "$evaluator" "$EVALUATOR_PATH" <<'PY'
import sys
source = open(sys.argv[1]).read()
old = '''        if crashed:
            cmd2 = "ps -ef | grep '-graphicsadapter="+ str(args.gpu_rank) + "' | grep -v grep | awk '{print $2}' | xargs -r kill -9"
            server = subprocess.Popen(cmd2, shell=True, preexec_fn=os.setsid)
            atexit.register(os.killpg, server.pid, signal.SIGKILL)
'''
if source.count(old) != 1:
    raise SystemExit('Unexpected evaluator cleanup code; inspect it before running safely')
open(sys.argv[2], 'w').write(source.replace(old, ''))
PY
printf 'Allocated CUDA devices: %s; model: %s; CARLA Vulkan adapter: %s\n' "$CUDA_VISIBLE_DEVICES" "$MODEL_CUDA_DEVICE" "$GPU_RANK"
printf 'Verified CARLA Vulkan adapter %s matches the first allocated CUDA device.\n' "$GPU_RANK"
nvidia-smi --query-gpu=index,uuid,pci.bus_id,name,memory.total --format=csv || true
"$REPO_DIR/scripts/run_closed_loop_vad_cluster.sh" --one-scenario
