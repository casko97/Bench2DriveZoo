#!/usr/bin/env bash
#SBATCH --job-name=vad-v004-eval
#SBATCH --gres=gpu:1
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --time=24:00:00
#SBATCH --constraint=arwen
#SBATCH --output=vad-v004-%j.out
#SBATCH --error=vad-v004-%j.err

set -euo pipefail

# Submit from the repository root. Override these environment variables at
# submission time to match the paths on the selected compute node.
REPO_DIR=${REPO_DIR:-${SLURM_SUBMIT_DIR:-$PWD}}
CONDA_BASE=${CONDA_BASE:-/Midgard/home/casko/miniforge3}
CONDA_ENV=${CONDA_ENV:-b2d_zoo.venv}
DATA_ROOT=${DATA_ROOT:-/local_storage/users/casko/dataset/B2D-V0.0.4}
INFO_DIR=${INFO_DIR:-/local_storage/users/casko/dataset/infos}
ANN_FILE=${ANN_FILE:-$INFO_DIR/b2d_infos_val_meta.pkl}
MAP_FILE=${MAP_FILE:-$INFO_DIR/b2d_map_infos.pkl}
CHECKPOINT=${CHECKPOINT:-/local_storage/users/casko/cpts/vad_b2d_base.pth}
WORKERS=${WORKERS:-4}

cd "$REPO_DIR"
[[ -f "$CONDA_BASE/etc/profile.d/conda.sh" ]] || { echo "Missing Conda initialization: $CONDA_BASE/etc/profile.d/conda.sh" >&2; exit 1; }
# Conda activation hooks can reference unset variables.
set +u
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"
set -u
PYTHON=$(command -v python)
echo "Activated Conda environment: $CONDA_PREFIX (Python: $PYTHON)"
for file in "$PYTHON" "$ANN_FILE" "$MAP_FILE" "$CHECKPOINT"; do
    [[ -f "$file" ]] || { echo "Missing file: $file" >&2; exit 1; }
done
[[ -d "$DATA_ROOT/v0.0.4" ]] || { echo "Missing extracted routes: $DATA_ROOT/v0.0.4" >&2; exit 1; }

# The meta pickle records the clip directory used at preparation time.
"$PYTHON" - "$ANN_FILE" <<'PY'
import os, pickle, sys
with open(sys.argv[1], 'rb') as f:
    meta = pickle.load(f)
clip_dir = meta['infos_dir_name']
if not os.path.isdir(clip_dir):
    raise SystemExit('Metadata clip directory does not exist: ' + clip_dir)
print('Per-route metadata:', clip_dir, flush=True)
PY

echo "Job ${SLURM_JOB_ID:-manual} on ${SLURMD_NODENAME:-$(hostname)}"
echo "Dataset: $DATA_ROOT; annotations: $ANN_FILE; maps: $MAP_FILE"
export PYTHONPATH="$REPO_DIR/adzoo:${PYTHONPATH:-}"
args=()
if [[ -n ${MAX_SAMPLES:-} ]]; then args+=(--max-samples "$MAX_SAMPLES"); fi
"$PYTHON" adzoo/vad/test.py adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py "$CHECKPOINT" \
    --split val --eval bbox "${args[@]}" --cfg-options \
    "data.val.data_root=$DATA_ROOT" "data.val.ann_file=$ANN_FILE" \
    "data.val.map_file=$MAP_FILE" "data.workers_per_gpu=$WORKERS"
