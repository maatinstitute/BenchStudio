"""Thin command-line adapter for System + Benchmark + EvaluationConfig."""
import argparse
import asyncio
from dataclasses import asdict
import json
import sys
from pathlib import Path

from .evaluation_engine import EvaluationConfig
from .pipeline import pipeline
from .system_pipeline import System, Benchmark


def main(argv=None):
    try:
        return _main(argv)
    except (ValueError, TypeError, ImportError, OSError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


def _main(argv=None):
    parser = argparse.ArgumentParser(prog="benchstudio evaluate")
    parser.add_argument("--system", required=True, help="Installed system backend, or model ID with --backend")
    parser.add_argument("--system-revision", required=True)
    parser.add_argument("--backend", help="Pretrained backend, e.g. vllm")
    parser.add_argument("--benchmark", required=True, help="Installed benchmark recipe name")
    parser.add_argument("--benchmark-revision", required=True)
    parser.add_argument("--run-id", default="evaluation")
    parser.add_argument("--output-dir", "--output", dest="output", type=Path, default=Path("runs/evaluation"))
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--timeout", type=float)
    parser.add_argument("--async", dest="asynchronous", action="store_true")
    parser.add_argument("--check", action="store_true", help="Check configuration/dependencies without running trials")
    args = parser.parse_args(argv)
    config = EvaluationConfig(args.run_id, args.batch_size, args.concurrency, args.timeout, args.output)
    system = (System.from_pretrained(args.system, revision=args.system_revision, backend=args.backend)
              if args.backend else System.from_backend(args.system, revision=args.system_revision))
    benchmark = Benchmark.load(args.benchmark, revision=args.benchmark_revision)
    evaluation = pipeline("evaluate", system=system, benchmark=benchmark, config=config)
    check = evaluation.check(mode="async" if args.asynchronous else "sync")
    if args.check:
        print(json.dumps(asdict(check), indent=2))
        return 0 if check.configuration_valid else 1
    if not check.configuration_valid:
        parser.error("; ".join(check.issues))
    result = asyncio.run(evaluation.arun()) if args.asynchronous else evaluation.run()
    print(result.summary())
    return 0
