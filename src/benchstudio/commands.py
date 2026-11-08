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
    if argv[0] == "evaluate" and any(
            arg == "--recipe" or arg.startswith("--recipe=") for arg in argv[1:]):
        from .recipe_cli import main as evaluate_recipe
        return evaluate_recipe(argv[1:])
    if argv[0] == "evaluate":
        from .system_cli import main as evaluate_system
        return evaluate_system(argv[1:])
    if argv[0] in ("run", "verify", "package", "doctor"):
        from .preparation_cli import main as prepare
        return prepare(argv)
    parser.parse_args(argv)
    return 2


if __name__ == "__main__":
    sys.exit(main())
