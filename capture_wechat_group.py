#!/usr/bin/env python3
"""CLI entrypoint for the WeChat evidence capture tool."""

from __future__ import annotations

import sys

from capture_core import CaptureAbort, main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CaptureAbort as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
