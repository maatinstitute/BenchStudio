#!/usr/bin/env bash

set -euo pipefail

python -m pytest -q
python -m pytest -q tests/test_ci_smoke.py
python -m compileall -q src tests examples scripts

echo "BenchStudio local CI gate passed"
