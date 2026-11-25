#!/usr/bin/env bash
# Group routes by town while retaining the evaluator's fresh world load per route.
set -euo pipefail
export BATCH_GROUP_BY_TOWN=1
exec bash "$(dirname "${BASH_SOURCE[0]}")/submit_closedloop_vad_batches.sh" "$@"
