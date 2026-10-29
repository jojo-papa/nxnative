#!/usr/bin/env python3
"""Convert a standard XCI into metadata-grouped NSP files without altering NCAs."""
import argparse
from pathlib import Path
import sys

XCI = ''
KEYS = ''
EXTRACTOR = ''
OUTPUT_DIR = ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('xci', nargs='?', default=XCI)
    parser.add_argument('--keys', default=KEYS)
    parser.add_argument('--extractor', default=EXTRACTOR, help='nx_extract executable with --catalog support')
    parser.add_argument('--out', default=OUTPUT_DIR)
    args = parser.parse_args()
    if not all((args.xci, args.keys, args.extractor, args.out)):
        parser.error('Set the Settings values or provide xci, --keys, --extractor and --out')
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from webui.packages import convert
    for path in convert(args.xci, args.out, args.extractor, args.keys): print(path)


if __name__ == '__main__': main()
