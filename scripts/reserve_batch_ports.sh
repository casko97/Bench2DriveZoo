#!/usr/bin/env bash
# Source this file: reserve a slot on this node for the lifetime of the caller.
# Each slot includes CARLA RPC, its adjacent streaming ports, and Traffic Manager.
command -v flock >/dev/null 2>&1 || { echo 'flock is required to reserve batch ports' >&2; exit 1; }
port_lock_dir="${BATCH_PORT_LOCK_DIR:-/tmp/bench2drive-port-locks-${UID}}"
mkdir -p "$port_lock_dir"
port_slot_start=$(( ${SLURM_JOB_ID:-0} % 1000 ))
port_slot_found=0
for ((port_slot_offset=0; port_slot_offset<1000; port_slot_offset++)); do
    port_slot=$(( (port_slot_start + port_slot_offset) % 1000 ))
    port_candidate=$((20000 + port_slot * 10))
    exec {port_lock_fd}>"$port_lock_dir/slot_${port_slot}.lock"
    if flock -n "$port_lock_fd" && python3 - "$port_candidate" <<'PY'
import socket
import sys
base = int(sys.argv[1])
sockets = []
try:
    for port in (base, base + 1, base + 2, base + 4):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sockets.append(sock)
        sock.bind(('0.0.0.0', port))
except OSError:
    sys.exit(1)
finally:
    for sock in sockets:
        sock.close()
PY
    then
        export PORT="$port_candidate" TM_PORT="$((port_candidate + 4))"
        port_slot_found=1
        break
    fi
    exec {port_lock_fd}>&-
done
if ((port_slot_found == 0)); then
    echo 'Could not reserve a free CARLA and Traffic Manager port slot' >&2
    exit 1
fi
printf 'Reserved node-local CARLA RPC port %s and Traffic Manager port %s (slot %s).\n' "$PORT" "$TM_PORT" "$port_slot"
