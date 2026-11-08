"""CLI bridge for installed scientific pipelines; scientific rules stay in recipes."""
import argparse
import subprocess
import sys

from .backend_loading import load_backend
from .pipeline import pipeline


def main(argv=None):
    try:
        return _main(argv)
    except (OSError, ValueError, TypeError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _main(argv=None):
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument("--recipe", required=True)
    selected, _ = selector.parse_known_args(argv)
    factory = load_backend("benchstudio.pipelines", selected.recipe)
    if not callable(getattr(factory, "add_cli_args", None)) or not callable(
            getattr(factory, "options_from_args", None)):
        raise ValueError("installed recipe does not provide a command-line configuration")
    parser = argparse.ArgumentParser(prog="benchstudio evaluate")
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--check", action="store_true", help="Read-only preparation; no campaign execution")
    factory.add_cli_args(parser)
    args = parser.parse_args(argv)
    evaluation = pipeline(args.recipe, **factory.options_from_args(args))
    result = evaluation.check() if args.check else evaluation.run()
    print(result.summary())
    if args.check:
        return 0 if result.technical_ready and getattr(result, "execution_authorized", None) is not False else 1
    return 0 if getattr(result, "successful", None) is not False else 1
