#!/usr/bin/env bash

set -euo pipefail

PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m pytest -q tests/test_ci_smoke.py
PYTHONPATH=src python -m compileall -q src tests examples scripts

echo "BenchStudio local CI gate passed"
