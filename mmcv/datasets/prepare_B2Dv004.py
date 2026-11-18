#!/usr/bin/env python3
"""Prepare Bench2Drive v0.0.4 route archives for the VAD data pipeline.

The upstream v0.0.4 protocol ships a fixed 44-route validation manifest. All
other routes are training data. This script preserves that train/validation
protocol and delegates frame conversion to ``prepare_B2D.py``. Its default
paths are relative to this file, so it can be called from any working directory.

Typical use::

    # After the Hugging Face download has finished:
    python prepare_B2Dv004.py --extract --workers 16

The generated manifest is ``data/splits/bench2drive_v0.0.4_train_val_test_\
split.json``.  It records the seed and ratios used, and can be passed back with
``--split-manifest`` to reproduce exactly the same preparation later.
"""

import argparse
import json
import os
from pathlib import Path
import tarfile


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_ARCHIVE_DIR = REPO_ROOT / 'Bench2Drive-V0.0.4'
DEFAULT_DATA_ROOT = REPO_ROOT / 'data' / 'bench2drive'
DEFAULT_OUT_DIR = REPO_ROOT / 'data' / 'infos' / 'v0.0.4'
DEFAULT_BASE_MAP_INFOS = REPO_ROOT / 'data' / 'infos' / 'b2d_map_infos.pkl'
DEFAULT_MANIFEST = (REPO_ROOT / 'data' / 'splits' /
                    'bench2drive_train_val_split_v04.json')
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


def load_official_splits(path, routes):
    """Use the upstream 44-route validation list without modification."""
    if not routes:
        raise ValueError('No route archives or extracted route directories found.')
    with path.open(encoding='utf-8') as handle:
        manifest = json.load(handle)
    if set(manifest) != {'val'} or not isinstance(manifest['val'], list):
        raise ValueError(
            f'{path} is not the upstream v0.0.4 validation manifest.')

    validation_routes = manifest['val']
    if len(validation_routes) != 44 or len(set(validation_routes)) != 44:
        raise ValueError(
            f'{path} must contain the 44 unique upstream validation routes.')
    available_routes = set(routes)
    missing = sorted(set(validation_routes) - available_routes)
    if missing:
        preview = ', '.join(missing[:5])
        suffix = ' ...' if len(missing) > 5 else ''
        raise FileNotFoundError(
            f'{len(missing)} official validation routes are missing from the '
            f'download: {preview}{suffix}. Download the complete release '
            'before preparing the upstream-aligned split.')

    validation_set = set(validation_routes)
    return {
        'train': [f'{VERSION_DIR}/{route}' for route in routes
                  if route not in validation_set],
        'val': [f'{VERSION_DIR}/{route}' for route in validation_routes],
    }


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
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--extract', action='store_true',
                        help='Extract downloaded .tar.gz routes before preparing.')
    parser.add_argument('--write-split-only', action='store_true',
                        help='Verify the upstream split and exit without extracting or preparing.')
    parser.add_argument('--map', help='Process only this map through the base preparer.')
    parser.add_argument('--maps-only', action='store_true',
                        help='Process maps only through the base preparer.')
    parser.add_argument('--build-map-infos', action='store_true',
                        help='Build a separate v0.0.4 map-info file instead of reusing the base file.')
    parser.add_argument('--use-depth-occlusion-filter', action='store_true',
                        help='Enable depth-based box visibility filtering; requires the separate depth release.')
    args = parser.parse_args()

    extracted_dir = args.data_root / VERSION_DIR
    if not args.split_manifest.is_file():
        raise FileNotFoundError(
            f'Upstream v0.0.4 split manifest is missing: {args.split_manifest}')
    routes = route_names(args.archive_dir, extracted_dir)
    manifest = load_official_splits(args.split_manifest, routes)
    print('Using upstream split manifest:', args.split_manifest)
    print('Routes: train={}, val={}'.format(
        len(manifest['train']), len(manifest['val'])))
    if args.write_split_only:
        return

    if args.extract:
        extract_archives(args.archive_dir, extracted_dir,
                         [path.split('/', 1)[1] for split in ('train', 'val')
                          for path in manifest[split]])

    missing = [route for split in ('train', 'val') for route in manifest[split]
               if not (args.data_root / route / 'anno').is_dir()]
    if missing:
        raise FileNotFoundError(
            f'{len(missing)} routes are not extracted under {extracted_dir}. '
            'Re-run with --extract after the download completes.')

    # Reuse the established frame conversion code while keeping all v0.0.4
    # products separate from base and mini artifacts.
    import prepare_B2D as base
    base.DATA_ROOT = str(args.data_root)
    base.OUT_DIR = str(args.out_dir)
    base.MAP_ROOT = str(args.data_root / 'maps')
    # The standard v0.0.4 release does not include depth images.
    base.FILTER_INVISINLE = args.use_depth_occlusion_filter
    args.out_dir.mkdir(parents=True, exist_ok=True)
    if not DEFAULT_BASE_MAP_INFOS.is_file():
        raise FileNotFoundError(
            f'Shared map infos are missing: {DEFAULT_BASE_MAP_INFOS}.')
    print('Reusing shared map infos:', DEFAULT_BASE_MAP_INFOS)
    if args.maps_only or args.map:
        if args.build_map_infos:
            base.gengrate_map(base.MAP_ROOT, args.map)
        return

    for split in ('train', 'val'):
        print(f'Processing {split} data...')
        base.generate_infos(manifest[split], args.workers, split)
    if args.build_map_infos:
        print('Processing map data...')
        base.gengrate_map(base.MAP_ROOT)
    print('Finished.')


if __name__ == '__main__':
    main()
