#!/usr/bin/env python3
"""Verify a IVal source-snapshot manifest against a local checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    try:
        from ival.source_snapshot import verify_source_snapshot

        result = verify_source_snapshot(args.manifest, args.source_root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
