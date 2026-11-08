"""Unified BenchStudio command line; execution logic lives in the Python APIs."""
from __future__ import annotations

import argparse
import sys


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="benchstudio", description="Evaluate AI systems and manage reproducible execution.")
    parser.add_argument("command", nargs="?", choices=("run", "verify", "package", "doctor", "evaluate"))
    if not argv or argv[0] in ("-h", "--help"):
        parser.print_help()
        return 0
    if argv[0] == "evaluate":
        from .cli import main as evaluate
        return evaluate(argv[1:])
    if argv[0] in ("run", "verify", "package", "doctor"):
        from .preparation_cli import main as prepare
        return prepare(argv)
    parser.parse_args(argv)
    return 2


if __name__ == "__main__":
    sys.exit(main())
