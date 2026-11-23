#!/usr/bin/env python3
"""Create rollout GIFs from saved PNG frames using Pillow."""
import argparse
from pathlib import Path

from PIL import Image

VIEWS = {'rgb_front', 'rgb_front_left', 'rgb_front_right',
         'rgb_back', 'rgb_back_left', 'rgb_back_right', 'bev'}


def create_gif(frame_dir):
    paths = []
    index = 0
    while True:
        path = frame_dir / ('%04d.png' % index)
        if not path.is_file():
            break
        paths.append(path)
        index += 1
    if not paths:
        return None
    frames = []
    try:
        for path in paths:
            with Image.open(path) as image:
                image = image.convert('RGB')
                if image.width > 960:
                    image = image.resize((960, max(1, round(image.height * 960 / image.width))), Image.Resampling.LANCZOS)
                frames.append(image.convert('P', palette=Image.Palette.ADAPTIVE, colors=128))
        output = frame_dir.with_suffix('.gif')
        frames[0].save(output, save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=False)
        return output
    finally:
        for frame in frames:
            frame.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir', type=Path, help='Run artifact directory containing saved view folders')
    args = parser.parse_args()
    if not args.run_dir.is_dir():
        parser.error('Run directory does not exist: %s' % args.run_dir)
    created = 0
    for frame_dir in sorted(p for p in args.run_dir.rglob('*') if p.is_dir() and p.name in VIEWS):
        output = create_gif(frame_dir)
        if output:
            print('Created GIF: %s' % output, flush=True)
            created += 1
    if not created:
        print('No PNG sequences found under %s; no GIFs created.' % args.run_dir)


if __name__ == '__main__':
    main()
