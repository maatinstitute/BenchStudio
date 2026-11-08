"""Command-line access to source preparation; no benchmark-specific rules."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .preparation import SourcePackage, SourceVerificationError, check_imports
from .processes import ProcessFailure


def main(argv=None):
    parser = argparse.ArgumentParser(prog="benchstudio", description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    for operation in ("verify", "package", "run"):
        command = sub.add_parser(operation)
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--root", type=Path, required=True)
        if operation == "package":
            command.add_argument("--output", type=Path, required=True)
        if operation == "run":
            command.add_argument("--python", required=True)
            command.add_argument("--entrypoint", required=True)
            command.add_argument("--log-dir", type=Path, required=True)
            command.add_argument("--timeout", type=float)
            command.add_argument("--check-import", action="append", default=[], metavar="MODULE")
            command.add_argument("--import-timeout", type=float, default=60)
            command.add_argument("args", nargs=argparse.REMAINDER,
                                 help="Native entry-point arguments after --")
    imports = sub.add_parser("doctor")
    imports.add_argument("--python", required=True)
    imports.add_argument("--log-dir", type=Path, required=True)
    imports.add_argument("--timeout", type=float, default=60)
    imports.add_argument("modules", nargs="+")
    args = parser.parse_args(argv)
    try:
        if args.operation == "doctor":
            report = check_imports(*args.modules, python=args.python,
                                   log_dir=args.log_dir, timeout=args.timeout)
        else:
            sources = SourcePackage.from_manifest(args.manifest, root=args.root)
            report = sources.verify()
            if args.operation == "verify":
                print(json.dumps(report, indent=2))
                return 0 if report["valid"] else 1
            if not report["valid"]:
                raise SourceVerificationError(repr(report["mismatches"]))
            if args.operation == "package":
                report = {"archive": str(args.output), "sha256": sources.archive(args.output)}
            else:
                # Neither verification nor diagnostic imports consume task permissions.
                # The existing native entry point retains its task-specific guards.
                if args.check_import:
                    check_imports(*args.check_import, python=args.python,
                                  log_dir=args.log_dir / "imports", timeout=args.import_timeout)
                native_args = args.args[1:] if args.args[:1] == ["--"] else args.args
                # run() checks hashes again after any explicit import diagnostic.
                receipt = sources.run(args.entrypoint, python=args.python, args=native_args,
                                      log_dir=args.log_dir, timeout=args.timeout)
                report = {"receipt": str(receipt)}
        print(json.dumps(report, indent=2))
        return 0
    except (OSError, ValueError, ProcessFailure) as error:
        print("error: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
