#!/usr/bin/env python3
"""Verify a BenchStudio source-snapshot manifest against a local checkout."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def verify_snapshot(manifest_path: Path, source_root: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != "benchstudio_source_snapshot_v1":
        raise ValueError("unsupported source snapshot manifest")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise ValueError("source snapshot files must be a non-empty mapping")
    mismatches: list[dict[str, str]] = []
    checked = 0
    root = source_root.resolve()
    for relative, expected in sorted(files.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("source snapshot paths and digests must be strings")
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"source snapshot path escapes source root: {relative}") from exc
        if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
            raise ValueError(f"invalid expected SHA-256 for {relative}")
        checked += 1
        if not candidate.is_file():
            mismatches.append({"path": relative, "reason": "missing"})
            continue
        actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append({"path": relative, "reason": "digest_mismatch", "actual": actual})
    return {
        "schema": "benchstudio.source_snapshot_verification.v1",
        "repository": manifest.get("repository"),
        "commit": manifest.get("commit"),
        "source_root": str(root),
        "checked_files": checked,
        "mismatches": mismatches,
        "valid": not mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("source_root", type=Path)
    args = parser.parse_args()
    try:
        result = verify_snapshot(args.manifest, args.source_root)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
