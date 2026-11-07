#!/usr/bin/env python3
"""Run the public direct-input API with a synthetic policy and environment.

This validates BenchStudio's Python path only. It does not load a model,
start a simulator, or measure task performance.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import benchstudio as bs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="new or resumable run directory")
    args = parser.parse_args()

    run = bs.pipeline(
        "robotics-evaluation",
        task={"id": "pick-cube", "revision": "fixture-v1"},
        model="mock",
        environment={"adapter": "mock-simulator", "kind": "simulator"},
        seeds=[7, 8],
        conditions=[{"id": "baseline"}],
        run_id="direct-api-quickstart",
        output_dir=args.output_dir,
        execution="mock",
    )()

    print(run.summary())
    print(run.analyze().summary())


if __name__ == "__main__":
    main()
