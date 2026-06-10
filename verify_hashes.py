#!/usr/bin/env python3
"""Verify sha256sums.txt for a WeChat evidence capture folder."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify files listed in sha256sums.txt.")
    parser.add_argument("evidence_dir", nargs="?", default=".", help="Evidence folder containing sha256sums.txt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    sums_path = evidence_dir / "sha256sums.txt"
    if not sums_path.exists():
        print(f"ERROR: Missing {sums_path}")
        return 2

    checked = 0
    failures: list[str] = []
    listed_paths: set[Path] = set()
    for line_number, raw_line in enumerate(sums_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if "  " not in line:
            failures.append(f"line {line_number}: malformed entry")
            continue
        expected, relpath = line.split("  ", 1)
        target = evidence_dir / relpath
        listed_paths.add(target.resolve())
        if not target.exists():
            failures.append(f"{relpath}: missing")
            continue
        actual = hash_file(target)
        checked += 1
        if actual.lower() != expected.lower():
            failures.append(f"{relpath}: hash mismatch expected={expected} actual={actual}")

    current_files = {
        p.resolve()
        for p in evidence_dir.rglob("*")
        if p.is_file() and p.name != "sha256sums.txt" and "_tmp" not in p.relative_to(evidence_dir).parts
    }
    extras = sorted(current_files - listed_paths)

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
        for path in extras[:20]:
            print(f"  extra: {path.relative_to(evidence_dir).as_posix()}")
        if len(extras) > 20:
            print("  ...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
