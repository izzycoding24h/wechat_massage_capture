#!/usr/bin/env python3
"""Verify sha256sums.txt for a WeChat evidence capture folder."""

from __future__ import annotations

import argparse
from pathlib import Path

from capture_core import verify_evidence_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify files listed in sha256sums.txt.")
    parser.add_argument("evidence_dir", nargs="?", default=".", help="Evidence folder containing sha256sums.txt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    result = verify_evidence_dir(evidence_dir)
    checked = result["checked"]
    failures = result["failures"]
    extras = result["extras"]

    if failures:
        print("FAILED")
        for failure in failures:
            print(f"  {failure}")
        if extras:
            print("")
            print(f"Note: {len(extras)} extra file(s) are not listed in sha256sums.txt.")
        return 1

    print(f"OK: verified {checked} file(s).")
    if extras:
        print(f"WARNING: {len(extras)} extra file(s) are not listed in sha256sums.txt.")
        for relpath in extras[:20]:
            print(f"  extra: {relpath}")
        if len(extras) > 20:
            print("  ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
