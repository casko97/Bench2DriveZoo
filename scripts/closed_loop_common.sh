#!/usr/bin/env bash
# Shared implementation for the standard and feedback closed-loop launchers.
#
# Optional overrides:
#   BENCH2DRIVE_ROOT, B2D_ZOO_VENV, CARLA_ROOT, GPU_RANK, ROUTES,
#   CHECKPOINT_ENDPOINT, SAVE_PATH, SAVE_VIEWS, SAVE_JPEG_ROUNDTRIP, PLANNER_TYPE, TEAM_AGENT, TEAM_CONFIG,
#   TRAFFIC_MANAGER_SEED (default 0; passed to Bench2Drive's evaluator),
#   CARLA_SENSOR_NOISE_SEED (default 0; used for GNSS and IMU noise),
#   FEEDBACK_TRIGGERS (default 1; 0 disables collision/route-lane logging),
#   FEEDBACK_TRIGGER_CONFIG (default feedback_pipeline/trigger_config.json),
#   FEEDBACK_CAPTURE_WINDOWS (default 1), FEEDBACK_WINDOW_CONFIG (window settings JSON),
#   FEEDBACK_ROUND_ID (default: launch run ID),
#   SUSTAINED_COLLISION_FRAMES (default 1, 0 disables early stopping),
#   SPLIT (train, val, test, all). An existing checkpoint JSON resumes
#   automatically; otherwise a timestamped fresh checkpoint is created.
set -euo pipefail

launcher_mode="${1:?launcher mode required}"
shift
case "${launcher_mode}" in
    standard|feedback) ;;
    *) printf 'Unknown launcher mode: %s\n' "${launcher_mode}" >&2; exit 2 ;;
esac

zoo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
bench2drive_root="${BENCH2DRIVE_ROOT:-"${zoo_root}/../Bench2Drive"}"
venv_dir="${B2D_ZOO_VENV:-"${zoo_root}/b2d_zoo.venv"}"
carla_root="${CARLA_ROOT:-"${zoo_root}/../Carla"}"
output_root="${zoo_root}/outputs/closed_loop"
evaluator_wrapper="${zoo_root}/scripts/run_evaluator_with_progress.py"
if [[ "${launcher_mode}" == feedback ]]; then
    output_root="${zoo_root}/outputs/feedback_closed_loop"
    evaluator_wrapper="${zoo_root}/scripts/run_feedback_evaluator.py"
fi
feedback_trigger_config="${FEEDBACK_TRIGGER_CONFIG:-${zoo_root}/feedback_pipeline/trigger_config.json}"
feedback_window_config="${FEEDBACK_WINDOW_CONFIG:-${zoo_root}/feedback_pipeline/window_config.json}"
if [[ "${feedback_trigger_config}" != /* ]]; then
    feedback_trigger_config="${PWD}/${feedback_trigger_config}"
fi
if [[ "${feedback_window_config}" != /* ]]; then
    feedback_window_config="${PWD}/${feedback_window_config}"
fi

gpu_rank="${GPU_RANK:-0}"
traffic_manager_seed="${TRAFFIC_MANAGER_SEED:-0}"
sensor_noise_seed="${CARLA_SENSOR_NOISE_SEED:-0}"
split="${SPLIT:-all}"
routes="${ROUTES:-leaderboard/data/bench2drive_0.0.4_val.xml}"
checkpoint_input="${CHECKPOINT_ENDPOINT:-}"
while (($#)); do
    case "$1" in
        --one-scenario)
            routes="${zoo_root}/one_scenario_town07.xml"
            split=all
            shift
            ;;
        --split)
            if (($# < 2)); then
                echo "--split requires train, val, test, or all" >&2
                exit 2
            fi
            split="$2"
            shift 2
            ;;
        --split=*)
            split="${1#*=}"
            shift
            ;;
        --routes)
            if (($# < 2)); then
                echo "--routes requires a CARLA routes XML path" >&2
                exit 2
            fi
            routes="$2"
            shift 2
            ;;
        --routes=*)
            routes="${1#*=}"
            shift
            ;;
        --checkpoint)
            if (($# < 2)); then
                echo "--checkpoint requires an existing checkpoint JSON path" >&2
                exit 2
            fi
            checkpoint_input="$2"
            shift 2
            ;;
        --checkpoint=*)
            checkpoint_input="${1#*=}"
            shift
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done
case "${split}" in
    train|val|test|all) ;;
    *) echo "Invalid split '${split}'; choose train, val, test, or all" >&2; exit 2 ;;
esac
if ! [[ "${traffic_manager_seed}" =~ ^-?[0-9]+$ ]]; then
    printf 'TRAFFIC_MANAGER_SEED must be an integer.\n' >&2
    exit 2
fi
if ! [[ "${sensor_noise_seed}" =~ ^-?[0-9]+$ ]]; then
    printf 'CARLA_SENSOR_NOISE_SEED must be an integer.\n' >&2
    exit 2
fi

resolve_from_bench2drive_root() {
    if [[ "$1" = /* ]]; then
        printf '%s\n' "$1"
    else
        printf '%s/%s\n' "${bench2drive_root}" "$1"
    fi
}

source_routes="$(resolve_from_bench2drive_root "${routes}")"
selected_routes="${source_routes}"
heartbeat_pid=""
cleanup() {
    if [[ -n "${heartbeat_pid}" ]]; then
        kill "${heartbeat_pid}" 2>/dev/null || true
        wait "${heartbeat_pid}" 2>/dev/null || true
    fi
    if [[ "${selected_routes}" != "${source_routes}" ]]; then
        rm -f "${selected_routes}"
    fi
}
trap cleanup EXIT
if [[ "${split}" != all ]]; then
    selected_routes="$(mktemp "${TMPDIR:-/tmp}/b2d_official_${split}_routes_XXXXXX.xml")"
fi
run_name="${split}"
resume_enabled=false
if [[ -n "${checkpoint_input}" ]]; then
    checkpoint_endpoint="$(resolve_from_bench2drive_root "${checkpoint_input}")"
    if [[ ! -f "${checkpoint_endpoint}" ]]; then
        printf 'Checkpoint JSON does not exist, so it cannot be resumed: %s\n' "${checkpoint_endpoint}" >&2
        exit 1
    fi
    run_id="$(basename "${checkpoint_endpoint}" .json)"
    resume_enabled=true
else
    timestamp="$(date +%Y%m%d_%H%M%S_%N)"
    run_id="eval_vad_v0.0.4_${run_name}_${timestamp}"
    checkpoint_endpoint="${output_root}/${run_id}.json"
fi
save_path="${SAVE_PATH:-$(dirname "${checkpoint_endpoint}")/${run_id}}"
if [[ "${save_path}" != /* ]]; then
    save_path="${bench2drive_root}/${save_path}"
fi
mkdir -p "${save_path}"
exec > >(tee -a "${save_path}/run.log") 2>&1
printf '\n[launcher] Starting run at %s\n' "$(date --iso-8601=seconds)"
printf 'Console log: %s/run.log\n' "${save_path}"
printf 'Checkpoint: %s\n' "${checkpoint_endpoint}"
printf 'Run artifacts: %s\n' "${save_path}"
planner_type="${PLANNER_TYPE:-only_traj}"
team_agent="${TEAM_AGENT:-leaderboard/team_code/vad_b2d_agent.py}"
team_config="${TEAM_CONFIG:-Bench2DriveZoo/adzoo/vad/configs/VAD/VAD_base_e2e_b2d.py+Bench2DriveZoo/ckpts/vad_b2d_base/vad_b2d_base.pth}"

required_paths=(
    "${venv_dir}/bin/activate"
    "${carla_root}/CarlaUE4.sh"
    "${bench2drive_root}/Bench2DriveZoo"
    "${bench2drive_root}/${team_agent}"
    "${bench2drive_root}/Bench2DriveZoo/ckpts/vad_b2d_base/vad_b2d_base.pth"
)
required_paths+=("${source_routes}")
for required_path in "${required_paths[@]}"; do
    if [[ ! -e "${required_path}" ]]; then
        printf 'Required path does not exist: %s\n' "${required_path}" >&2
        exit 1
    fi
done

mkdir -p "$(dirname "${checkpoint_endpoint}")"
source "${venv_dir}/bin/activate"
export CARLA_ROOT="${carla_root}"

cd "${bench2drive_root}"
if [[ "${split}" != all ]]; then
    python "${zoo_root}/scripts/select_closed_loop_split.py" \
        "${source_routes}" "${split}" "${selected_routes}"
fi

export CARLA_SERVER="${carla_root}/CarlaUE4.sh"
export PYTHONPATH="${PYTHONPATH:-}:${carla_root}/PythonAPI:${carla_root}/PythonAPI/carla:${carla_root}/PythonAPI/carla/dist/carla-0.9.15-py3.7-linux-x86_64.egg:leaderboard:leaderboard/team_code:scenario_runner"
export SCENARIO_RUNNER_ROOT=scenario_runner
export LEADERBOARD_ROOT=leaderboard
export CHALLENGE_TRACK_CODENAME=SENSORS
export PORT=30000
export TM_PORT=50000
export DEBUG_CHALLENGE=0
export REPETITIONS=1
export IS_BENCH2DRIVE=True
export PLANNER_TYPE="${planner_type}"
export SAVE_PATH="${save_path}"
if [[ "${launcher_mode}" == feedback ]]; then
    export FEEDBACK_TRIGGERS="${FEEDBACK_TRIGGERS:-1}"
    export FEEDBACK_CAPTURE_WINDOWS="${FEEDBACK_CAPTURE_WINDOWS:-1}"
    export FEEDBACK_WINDOW_CONFIG="${feedback_window_config}"
    export FEEDBACK_ROUND_ID="${FEEDBACK_ROUND_ID:-${run_id}}"
    export TRAFFIC_MANAGER_SEED="${traffic_manager_seed}"
fi
export ROUTES="${selected_routes}"
export SAVE_VIEWS="${SAVE_VIEWS-rgb_front,bev}"
printf 'Saved image views: %s\n' "${SAVE_VIEWS:-none}"
export SAVE_JPEG_ROUNDTRIP="${SAVE_JPEG_ROUNDTRIP:-1}"
if [[ "${SAVE_JPEG_ROUNDTRIP}" != 0 && "${SAVE_JPEG_ROUNDTRIP}" != 1 ]]; then
    printf 'SAVE_JPEG_ROUNDTRIP must be 0 or 1.\n' >&2
    exit 2
fi
printf 'JPEG round trip for saved camera images: %s\n' "${SAVE_JPEG_ROUNDTRIP}"
export B2D_TELEMETRY=1
export CARLA_SENSOR_NOISE_SEED="${sensor_noise_seed}"
export GPU_RANK="${gpu_rank}"
export SUSTAINED_COLLISION_FRAMES="${SUSTAINED_COLLISION_FRAMES:-1}"
if ! [[ "${SUSTAINED_COLLISION_FRAMES}" =~ ^[0-9]+$ ]]; then
    printf 'SUSTAINED_COLLISION_FRAMES must be a non-negative integer.\n' >&2
    exit 2
fi
printf 'Sustained collision stop threshold: %s consecutive frames (0 disables).\n' "${SUSTAINED_COLLISION_FRAMES}"
printf 'Telemetry: %s/telemetry.jsonl (30-second samples; GPU inference timing synchronizes CUDA)\n' "${save_path}"
printf 'Live benchmark events: %s/live_events.jsonl\n' "${save_path}"
if [[ "${launcher_mode}" == feedback && "${FEEDBACK_TRIGGERS:-0}" == 1 ]]; then
    export FEEDBACK_TRIGGER_CONFIG="${feedback_trigger_config}"
    printf 'Feedback triggers: %s/feedback_triggers.jsonl\n' "${save_path}"
    printf 'Feedback trigger config: %s\n' "${FEEDBACK_TRIGGER_CONFIG}"
    if [[ "${FEEDBACK_CAPTURE_WINDOWS}" == 1 ]]; then
        printf 'Feedback window data: %s/feedback_data (config: %s)\n' "${save_path}" "${FEEDBACK_WINDOW_CONFIG}"
    fi
fi

resume_args=()
if [[ "${resume_enabled}" == true ]]; then
    resume_args+=(--resume=True)
fi

printf 'Routes: %s (split: %s)\n' "${selected_routes}" "${split}"
printf 'Traffic Manager seed: %s\n' "${traffic_manager_seed}"
printf 'CARLA GNSS/IMU noise seed: %s (IMU uses seed + 1)\n' "${sensor_noise_seed}"
printf 'Starting evaluator on GPU %s. It launches CARLA offscreen and waits 30 seconds before connecting.\n' "${gpu_rank}"
printf 'Evaluator output follows; periodic messages indicate elapsed time, not simulation progress.\n'
(
    elapsed=0
    while sleep 30; do
        elapsed=$((elapsed + 30))
        printf '[launcher] Evaluator has not returned after %s seconds; check messages above for simulation progress.\n' "${elapsed}"
    done
) &
heartbeat_pid=$!

if CUDA_VISIBLE_DEVICES="${gpu_rank}" python -u "${zoo_root}/scripts/supervise_evaluator.py" python -u "${evaluator_wrapper}" "${LEADERBOARD_ROOT}/leaderboard/leaderboard_evaluator.py" \
    --routes="${selected_routes}" \
    --repetitions="${REPETITIONS}" \
    --track="${CHALLENGE_TRACK_CODENAME}" \
    --checkpoint="${checkpoint_endpoint}" \
    --agent="${team_agent}" \
    --agent-config="${team_config}" \
    --debug="${DEBUG_CHALLENGE}" \
    --record="${RECORD_PATH:-}" \
    "${resume_args[@]}" \
    --port="${PORT}" \
    --traffic-manager-port="${TM_PORT}" \
    --traffic-manager-seed="${traffic_manager_seed}" \
    --gpu-rank="${gpu_rank}"; then
    printf '[launcher] Evaluator finished successfully.\n'
else
    status=$?
    printf '[launcher] Evaluator exited with status %s; see output above.\n' "${status}" >&2
    exit "${status}"
fi
kill "${heartbeat_pid}" 2>/dev/null || true
wait "${heartbeat_pid}" 2>/dev/null || true
heartbeat_pid=""

if command -v ffmpeg >/dev/null 2>&1; then
    generated_gifs=0
    for view in rgb_front rgb_front_left rgb_front_right rgb_back rgb_back_left rgb_back_right bev; do
        while IFS= read -r -d '' frame_dir; do
            [[ -f "${frame_dir}/0000.png" ]] || continue
            gif_path="${frame_dir}.gif"
            ffmpeg -hide_banner -loglevel error -y \
                -framerate 10 -i "${frame_dir}/%04d.png" \
                -vf "scale=w='min(960,iw)':h=-2:flags=lanczos,split[s0][s1];[s0]palettegen=stats_mode=diff:max_colors=128[p];[s1][p]paletteuse=dither=bayer" \
                -loop 0 "${gif_path}"
            printf 'Created GIF: %s\n' "${gif_path}"
            generated_gifs=$((generated_gifs + 1))
        done < <(find "${save_path}" -type d -name "${view}" -print0)
    done
    if ((generated_gifs == 0)); then
        printf 'No PNG sequences found under %s; no GIFs created.\n' "${save_path}"
    fi
else
    printf 'ffmpeg not found; skipped GIF creation.\n' >&2
fi
