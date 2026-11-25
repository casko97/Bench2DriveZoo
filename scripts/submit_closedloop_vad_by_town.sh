#!/usr/bin/env bash
# Group routes by town while retaining the evaluator's fresh world load per route.
set -euo pipefail
export BATCH_GROUP_BY_TOWN=1
# Throughput-oriented defaults. Set any variable explicitly to override it.
export MAX_CONCURRENT="${MAX_CONCURRENT:-3}"
export SAVE_VIEWS="${SAVE_VIEWS-}"
export SAVE_JPEG_ROUNDTRIP="${SAVE_JPEG_ROUNDTRIP:-0}"
export VAD_FAST_PIPELINE="${VAD_FAST_PIPELINE:-1}"
export B2D_TELEMETRY="${B2D_TELEMETRY:-0}"
exec bash "$(dirname "${BASH_SOURCE[0]}")/submit_closedloop_vad_batches.sh" "$@"
