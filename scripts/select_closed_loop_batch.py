#!/usr/bin/env python3
"""Select an ordered, zero-based batch of routes from a Bench2Drive XML."""
import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path


def load_routes(path):
    tree = ET.parse(path)
    routes = tree.getroot().findall('route')
    if not routes:
        raise ValueError('No route elements found in %s' % path)
    ids = [route.get('id') for route in routes]
    if any(not route_id for route_id in ids) or len(ids) != len(set(ids)):
        raise ValueError('Every route must have a unique, non-empty ID')
    return tree, routes


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be positive')
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('routes_xml', type=Path)
    parser.add_argument('--batch-size', type=positive_int, default=5)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--count', action='store_true', help='Print the number of batches')
    group.add_argument('--index', type=int, help='Zero-based batch index')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        tree, routes = load_routes(args.routes_xml)
        batches = math.ceil(len(routes) / args.batch_size)
        if args.count:
            if args.output is not None:
                parser.error('--output cannot be used with --count')
            print(batches)
            return
        if args.output is None:
            parser.error('--index requires --output')
        if args.index < 0 or args.index >= batches:
            parser.error('batch index must be between 0 and %d' % (batches - 1))
        start = args.index * args.batch_size
        selected = routes[start:start + args.batch_size]
        keep = set(selected)
        root = tree.getroot()
        for route in routes:
            if route not in keep:
                root.remove(route)
        tree.write(args.output, encoding='utf-8', xml_declaration=True)
        print('Batch %d/%d: routes %s (source positions %d-%d of %d)' %
              (args.index, batches - 1, ', '.join(route.get('id') for route in selected),
               start + 1, start + len(selected), len(routes)))
    except (OSError, ET.ParseError, ValueError) as exc:
        parser.exit(1, 'Batch selection failed: %s\n' % exc)


if __name__ == '__main__':
    main()
