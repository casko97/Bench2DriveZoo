#!/usr/bin/env python3
"""Prepare Bench2Drive v0.0.4 route archives for the VAD data pipeline.

The official v0.0.4 release does not ship a train/validation/test manifest.
This script creates one deterministically from the route names, then delegates
frame conversion to ``prepare_B2D.py``.  Its default paths are relative to this
file, so it can be called from any working directory.

Typical use::

    # After the Hugging Face download has finished:
    python prepare_B2Dv004.py --extract --workers 16

The generated manifest is ``data/splits/bench2drive_v0.0.4_train_val_test_\
split.json``.  It records the seed and ratios used, and can be passed back with
``--split-manifest`` to reproduce exactly the same preparation later.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_ARCHIVE_DIR = REPO_ROOT / 'Bench2Drive-V0.0.4'
DEFAULT_DATA_ROOT = REPO_ROOT / 'data' / 'bench2drive'
DEFAULT_OUT_DIR = REPO_ROOT / 'data' / 'infos' / 'v0.0.4'
DEFAULT_MANIFEST = (REPO_ROOT / 'data' / 'splits' /
                    'bench2drive_v0.0.4_train_val_test_split.json')
VERSION_DIR = 'v0.0.4'


def route_names(archive_dir, extracted_dir):
    """Return sorted route names from archives, or already extracted routes."""
    archives = sorted(archive_dir.glob('*.tar.gz'))
    if archives:
        return [archive.name[:-7] for archive in archives]

    if extracted_dir.is_dir():
        return sorted(
            path.name for path in extracted_dir.iterdir()
            if path.is_dir() and (path / 'anno').is_dir())
    return []


def split_routes(routes, seed, train_ratio, val_ratio):
    """Create a deterministic route split using a seeded SHA-256 ranking."""
    if not routes:
        raise ValueError('No route archives or extracted route directories found.')
    if not 0 < train_ratio < 1 or not 0 < val_ratio < 1 or train_ratio + val_ratio >= 1:
        raise ValueError('train_ratio and val_ratio must be positive and sum to less than 1.')

    ranked = sorted(
        routes,
        key=lambda route: hashlib.sha256(f'{seed}:{route}'.encode('utf-8')).hexdigest(),
    )
    count = len(ranked)
    train_end = int(count * train_ratio)
    val_end = train_end + int(count * val_ratio)
    # Keep every split non-empty when there are at least three routes.
    if count >= 3:
        train_end = max(1, train_end)
        val_end = max(train_end + 1, val_end)
        val_end = min(count - 1, val_end)
    return {
        'train': [f'{VERSION_DIR}/{route}' for route in ranked[:train_end]],
        'val': [f'{VERSION_DIR}/{route}' for route in ranked[train_end:val_end]],
        'test': [f'{VERSION_DIR}/{route}' for route in ranked[val_end:]],
    }


def write_manifest(path, routes, seed, train_ratio, val_ratio):
    splits = split_routes(routes, seed, train_ratio, val_ratio)
    manifest = {
        'dataset': 'Bench2Drive-V0.0.4',
        'seed': seed,
        'split_method': 'SHA-256 ranking of seed and route name',
        'ratios': {
            'train': train_ratio,
            'val': val_ratio,
            'test': 1 - train_ratio - val_ratio,
        },
        **splits,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
        handle.write('\n')
    return manifest


def extract_archives(archive_dir, destination, routes):
    """Extract only requested route archives, rejecting unsafe member paths."""
    destination.mkdir(parents=True, exist_ok=True)
    for route in routes:
        output = destination / route
        if output.is_dir():
            continue
        archive = archive_dir / f'{route}.tar.gz'
        if not archive.is_file():
            raise FileNotFoundError(f'Missing archive for route {route}: {archive}')
        print(f'Extracting {archive.name}...')
        with tarfile.open(archive, 'r:gz') as tar:
            for member in tar.getmembers():
                member_path = (destination / member.name).resolve()
                if os.path.commonpath((str(destination.resolve()), str(member_path))) != str(destination.resolve()):
                    raise ValueError(f'Unsafe archive member in {archive}: {member.name}')
            tar.extractall(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive-dir', type=Path, default=DEFAULT_ARCHIVE_DIR)
    parser.add_argument('--data-root', type=Path, default=DEFAULT_DATA_ROOT,
                        help='Parent of the v0.0.4 route directory.')
    parser.add_argument('--out-dir', type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument('--split-manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--seed', type=int, default=20261117)
    parser.add_argument('--train-ratio', type=float, default=0.8)
    parser.add_argument('--val-ratio', type=float, default=0.1)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--tmp-dir', default='tmp_data')
    parser.add_argument('--extract', action='store_true',
                        help='Extract downloaded .tar.gz routes before preparing.')
    parser.add_argument('--write-split-only', action='store_true',
                        help='Create the manifest and exit without extracting or preparing.')
    parser.add_argument('--regenerate-split', action='store_true',
                        help='Replace an existing manifest using the current route set and options.')
    parser.add_argument('--map', help='Process only this map through the base preparer.')
    parser.add_argument('--maps-only', action='store_true',
                        help='Process maps only through the base preparer.')
    args = parser.parse_args()

    extracted_dir = args.data_root / VERSION_DIR
    if args.split_manifest.is_file() and not args.regenerate_split:
        with args.split_manifest.open(encoding='utf-8') as handle:
            manifest = json.load(handle)
        if not all(split in manifest for split in ('train', 'val', 'test')):
            raise ValueError(f'Invalid split manifest: {args.split_manifest}')
        print('Using existing split manifest:', args.split_manifest)
    else:
        routes = route_names(args.archive_dir, extracted_dir)
        manifest = write_manifest(args.split_manifest, routes, args.seed,
                                  args.train_ratio, args.val_ratio)
        print('Wrote split manifest:', args.split_manifest)
    print('Routes: train={}, val={}, test={}'.format(
        len(manifest['train']), len(manifest['val']), len(manifest['test'])))
    if args.write_split_only:
        return

    if args.extract:
        extract_archives(args.archive_dir, extracted_dir,
                         [path.split('/', 1)[1] for split in ('train', 'val', 'test')
                          for path in manifest[split]])

    missing = [route for split in ('train', 'val', 'test') for route in manifest[split]
               if not (args.data_root / route / 'anno').is_dir()]
    if missing:
        raise FileNotFoundError(
            f'{len(missing)} routes are not extracted under {extracted_dir}. '
            'Re-run with --extract after the download completes.')

    # Reuse the established frame conversion code while keeping all v0.0.4
    # products separate from base and mini artifacts.
    import prepare_B2D as base
    base.DATAROOT = str(args.data_root)
    base.OUT_DIR = str(args.out_dir)
    base.MAP_ROOT = str(args.data_root / 'maps')
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if args.maps_only or args.map:
        base.gengrate_map(base.MAP_ROOT, args.map)
        return

    for split in ('train', 'val', 'test'):
        print(f'Processing {split} data...')
        base.process_list = []
        base.generate_infos(manifest[split], args.workers, split, args.tmp_dir)
    print('Processing map data...')
    base.gengrate_map(base.MAP_ROOT)
    print('Finished.')


if __name__ == '__main__':
    main()
