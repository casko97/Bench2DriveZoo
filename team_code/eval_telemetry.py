"""Optional, low-frequency runtime telemetry for closed-loop evaluations."""
import contextlib
import json
import os
import subprocess
import threading
import time
from collections import defaultdict
from pathlib import Path

_lock = threading.Lock()
_totals = defaultdict(float)
_counts = defaultdict(int)
_enabled = os.environ.get("B2D_TELEMETRY") == "1"


@contextlib.contextmanager
def measure(name, synchronize=None):
    if not _enabled:
        yield
        return
    if synchronize:
        synchronize()
    start = time.perf_counter()
    try:
        yield
    finally:
        if synchronize:
            synchronize()
        elapsed = time.perf_counter() - start
        with _lock:
            _totals[name] += elapsed
            _counts[name] += 1


def _cpu_sample():
    with open('/proc/stat') as f:
        fields = [int(v) for v in f.readline().split()[1:]]
    return sum(fields[:8]), fields[3] + fields[4]


def _memory():
    with open('/proc/meminfo') as f:
        values = {line.split(':', 1)[0]: int(line.split()[1]) for line in f if ':' in line}
    return {'total_mib': round(values['MemTotal'] / 1024),
            'available_mib': round(values['MemAvailable'] / 1024)}


def _gpu():
    try:
        result = subprocess.run(
            ['nvidia-smi', '-i', os.environ.get('GPU_RANK', '0'),
             '--query-gpu=utilization.gpu,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5, check=True)
        util, used, total = (float(v.strip()) for v in result.stdout.strip().split(','))
        return {'utilization_percent': util, 'memory_used_mib': used, 'memory_total_mib': total}
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def start_monitor(path, interval=30):
    """Write interval measurements to JSONL and stdout until the evaluator exits."""
    if not _enabled:
        return None
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    stop = threading.Event()

    def monitor():
        previous_cpu = _cpu_sample()
        previous_totals, previous_counts = {}, {}
        while not stop.wait(interval):
            now_cpu = _cpu_sample()
            delta = now_cpu[0] - previous_cpu[0]
            cpu = 100 * (1 - (now_cpu[1] - previous_cpu[1]) / delta) if delta else 0
            previous_cpu = now_cpu
            with _lock:
                totals, counts = dict(_totals), dict(_counts)
            timings = {}
            for name, total in totals.items():
                count = counts[name] - previous_counts.get(name, 0)
                if count:
                    timings[name] = {'calls': count, 'total_seconds': round(total - previous_totals.get(name, 0), 3),
                                     'mean_ms': round(1000 * (total - previous_totals.get(name, 0)) / count, 1)}
            previous_totals, previous_counts = totals, counts
            sample = {'time': time.strftime('%Y-%m-%dT%H:%M:%S%z'), 'interval_seconds': interval,
                      'host_cpu_percent': round(cpu, 1), 'host_memory': _memory(), 'gpu': _gpu(),
                      'timings': timings}
            with open(path, 'a') as f:
                f.write(json.dumps(sample) + '\n')
            print('[telemetry] ' + json.dumps(sample), flush=True)

    threading.Thread(target=monitor, daemon=True).start()
    return stop
