"""Supervise an evaluator and clean up its child processes on interruption (Linux)."""
import os
import signal
import subprocess
import sys
import time


def process_snapshot():
    processes = {}
    for entry in os.scandir('/proc'):
        if not entry.name.isdigit():
            continue
        try:
            with open(os.path.join(entry.path, 'stat')) as stream:
                fields = stream.read().rsplit(')', 1)[1].split()
            processes[int(entry.name)] = (int(fields[1]), fields[19])
        except (OSError, IndexError, ValueError):
            continue
    return processes


def descendants(root, processes):
    found = {root}
    while True:
        expanded = found | {pid for pid, (parent, _) in processes.items() if parent in found}
        if expanded == found:
            return found - {root}
        found = expanded


def main():
    if len(sys.argv) < 2:
        print('Usage: supervise_evaluator.py COMMAND [ARG ...]', file=sys.stderr)
        return 2
    interrupted = 0
    first_interrupt = None

    def request_stop(signum, frame):
        nonlocal interrupted, first_interrupt
        interrupted += 1
        if first_interrupt is None:
            first_interrupt = time.monotonic()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    process = subprocess.Popen(sys.argv[1:], start_new_session=True)
    tracked = {}
    forwarded = False

    while True:
        processes = process_snapshot()
        for pid in descendants(process.pid, processes):
            tracked[pid] = processes[pid][1]
        status = process.poll()
        if interrupted and not forwarded and status is None:
            print('[launcher] Interrupt received; requesting graceful shutdown. Press Ctrl+C again to force.', flush=True)
            try:
                os.kill(process.pid, signal.SIGINT)
            except ProcessLookupError:
                pass
            forwarded = True
        force = interrupted > 1 or (first_interrupt is not None and time.monotonic() - first_interrupt >= 15)
        if force:
            print('[launcher] Forcing shutdown; unfinished statistics may be lost.', flush=True)
        if status is not None or force:
            # CARLA starts a separate session. Kill only observed descendants whose
            # process IDs still have the same /proc start time, including orphans.
            for pid, start in tracked.items():
                if processes.get(pid, (None, None))[1] == start:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
            if status is None:
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            return 130 if interrupted else status
        time.sleep(0.2)


if __name__ == '__main__':
    sys.exit(main())
