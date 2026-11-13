#!/usr/bin/env bash

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
cd "$ROOT"

uv sync --locked --extra dev
uv run --locked ruff check .
uv run --locked mypy
uv run --locked python -m pytest -q
uv run --locked python -m compileall -q src tests examples scripts

echo "ReVa local CI gate passed"
