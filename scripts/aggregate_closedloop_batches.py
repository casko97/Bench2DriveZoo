#!/usr/bin/env python3
"""Merge closed-loop batch checkpoints and report route-level outcomes."""
import argparse
import json
import os
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('queue_dir', type=Path)
    parser.add_argument('--output', type=Path,
                        help='Merged checkpoint path (default: QUEUE/aggregate.json)')
    parser.add_argument('--report', type=Path,
                        help='Human-readable report path (default: QUEUE/aggregate_report.txt)')
    parser.add_argument('--bench2drive-root', default=os.environ.get('BENCH2DRIVE_ROOT'),
                        help='Bench2Drive checkout; defaults to BENCH2DRIVE_ROOT')
    return parser.parse_args()


def checkpoint_candidates(batch_dir):
    return sorted((path for path in batch_dir.glob('attempt_*/*.json')
                   if path.name not in ('aggregate.json',)),
                  key=lambda path: (path.parent.name, path.stat().st_mtime))


def select_checkpoints(queue_dir):
    selected = []
    warnings = []
    batch_dirs = sorted(path for path in queue_dir.glob('batch_*') if path.is_dir())
    for batch_dir in batch_dirs:
        candidates = checkpoint_candidates(batch_dir)
        if not candidates:
            warnings.append('%s: no checkpoint found' % batch_dir.name)
            continue
        # Attempt names contain the Slurm job id and timestamp; choosing the
        # newest attempt makes reruns replace an older failed attempt cleanly.
        chosen = candidates[-1]
        selected.append(chosen)
        if len(candidates) > 1:
            warnings.append('%s: selected newest attempt %s of %d' %
                            (batch_dir.name, chosen.parent.name, len(candidates)))
    return selected, warnings


def load(path):
    with path.open() as stream:
        data = json.load(stream)
    records = data.get('_checkpoint', {}).get('records', [])
    progress = data.get('_checkpoint', {}).get('progress', [])
    if not records or len(progress) != 2:
        raise ValueError('%s has no usable records/progress' % path)
    return data, records, progress


def route_report(records):
    lines = ['Route outcomes', '==============',
             'route_id\toutcome\tstatus\tscore_route\tscore_penalty\tscore_composed\tduration_system_s']
    for record in records:
        scores = record.get('scores', {})
        meta = record.get('meta', {})
        status = record.get('status', 'Unknown')
        outcome = 'SUCCESS' if status in ('Perfect', 'Completed') else 'FAILURE'
        lines.append('%s\t%s\t%s\t%s\t%s\t%s\t%s' % (
            record.get('route_id', '?'), outcome, status,
            scores.get('score_route', ''), scores.get('score_penalty', ''),
            scores.get('score_composed', ''), meta.get('duration_system', '')))
    return lines


def main():
    args = parse_args()
    queue_dir = args.queue_dir.resolve()
    if not queue_dir.is_dir():
        raise SystemExit('Queue directory does not exist: %s' % queue_dir)
    output = (args.output or queue_dir / 'aggregate.json').resolve()
    report = (args.report or queue_dir / 'aggregate_report.txt').resolve()
    paths, warnings = select_checkpoints(queue_dir)
    if not paths:
        raise SystemExit('No batch checkpoints found under %s' % queue_dir)

    all_records = []
    sensors = None
    expected_total = 0
    source_lines = []
    for path in paths:
        data, records, progress = load(path)
        expected_total += progress[1]
        source_lines.append('%s\t%s\t%d/%d records' %
                            (path.parent.parent.name, path, len(records), progress[1]))
        current_sensors = data.get('sensors', [])
        if sensors is None:
            sensors = current_sensors
        elif current_sensors != sensors:
            raise SystemExit('Sensor configuration differs between batch checkpoints: %s' % path)
        all_records.extend(records)

    route_ids = [record.get('route_id') for record in all_records]
    duplicates = sorted(route_id for route_id in set(route_ids)
                        if route_ids.count(route_id) > 1)
    if duplicates:
        raise SystemExit('Duplicate route records found: %s' % ', '.join(duplicates))
    actual_total = len(all_records)
    complete = actual_total == expected_total and all(
        record.get('status') not in ('Started', None) for record in all_records)

    # Use the upstream StatisticsManager so global scores and serial-evaluator
    # fields follow the benchmark's own implementation exactly.
    bench_root = args.bench2drive_root
    if not bench_root:
        raise SystemExit('Set BENCH2DRIVE_ROOT or pass --bench2drive-root')
    leaderboard_root = str(Path(bench_root) / 'leaderboard')
    runner_root = str(Path(bench_root) / 'scenario_runner')
    sys.path[:0] = [leaderboard_root, runner_root]
    from leaderboard.utils.checkpoint_tools import fetch_dict
    from leaderboard.utils.statistics_manager import StatisticsManager

    manager = StatisticsManager(str(output), str(report.with_suffix('.live.txt')))
    for path in paths:
        manager.add_file_records(str(path))
    manager.sort_records()
    manager.save_sensors(sensors or [])
    manager.save_progress(actual_total, expected_total)
    manager.save_entry_status('Started')
    if complete:
        manager.compute_global_statistics()
        manager.validate_and_write_statistics(True, False)
    else:
        manager.write_statistics()

    merged = fetch_dict(str(output))
    global_record = merged.get('_checkpoint', {}).get('global_record', {})
    values = dict(zip(merged.get('labels', []), merged.get('values', [])))
    successful = [r for r in all_records if r.get('status') in ('Perfect', 'Completed')]
    failed = [r for r in all_records if r not in successful]
    lines = ['Closed-loop batch aggregation', '============================',
             'Queue: %s' % queue_dir,
             'Batch checkpoints: %d' % len(paths),
             'Routes with records: %d/%d' % (actual_total, expected_total),
             'Complete: %s' % complete,
             'Successful route records: %d' % len(successful),
             'Failed/non-final route records: %d' % len(failed), '']
    if warnings:
        lines += ['Warnings:'] + ['- ' + warning for warning in warnings] + ['']
    lines += ['Global metrics']
    lines += ['-------------']
    for key in ('Avg. driving score', 'Avg. route completion', 'Avg. infraction penalty'):
        if key in values:
            lines.append('%s: %s' % (key, values[key]))
    if global_record:
        lines.append('Entry status: %s' % merged.get('entry_status', 'Unknown'))
    lines += ['', 'Selected checkpoints', '--------------------'] + source_lines + ['']
    lines += route_report(sorted(all_records, key=lambda r: r.get('route_id', '')))
    report.write_text('\n'.join(lines) + '\n')
    print('\n'.join(lines[:12]))
    print('Merged checkpoint: %s' % output)
    print('Report: %s' % report)
    return 0 if complete else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, ImportError) as exc:
        raise SystemExit('Aggregation failed: %s' % exc)
