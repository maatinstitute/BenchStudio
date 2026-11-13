#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

uv run --locked python -m pytest -q
uv run --locked python -m pytest -q tests/test_ci_smoke.py
uv run --locked python -m compileall -q src tests examples scripts

echo "BenchStudio local CI gate passed"
