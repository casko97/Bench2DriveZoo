#!/usr/bin/env python3
"""Write a deterministic 60/20/20 subset of a Bench2Drive routes XML."""

import argparse
import hashlib
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('routes_xml')
    parser.add_argument('split', choices=('train', 'val', 'test'))
    parser.add_argument('output_xml')
    parser.add_argument('--seed', type=int, default=20261117)
    args = parser.parse_args()

    tree = ET.parse(args.routes_xml)
    root = tree.getroot()
    routes = root.findall('route')
    if not routes:
        raise ValueError(f'No <route> entries found in {args.routes_xml}')

    ranked = sorted(
        routes,
        key=lambda route: hashlib.sha256(
            f"{args.seed}:{route.get('id', '')}".encode('utf-8')).hexdigest(),
    )
    count = len(ranked)
    train_end = int(count * 0.6)
    val_end = train_end + int(count * 0.2)
    selected = {
        'train': ranked[:train_end],
        'val': ranked[train_end:val_end],
        'test': ranked[val_end:],
    }[args.split]

    selected_ids = {id(route) for route in selected}
    for route in list(root.findall('route')):
        if id(route) not in selected_ids:
            root.remove(route)
    tree.write(args.output_xml, encoding='utf-8', xml_declaration=True)
    print(f'{args.split}: selected {len(selected)} of {count} routes')


if __name__ == '__main__':
    main()
