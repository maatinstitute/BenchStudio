"""CPU-only evaluation/comparison/result-export profile on synthetic scalar data."""
import cProfile
import json
import pstats
from statistics import median
from timeit import repeat

import benchstudio as bs


def fixture():
    values = list(range(4000))
    system = bs.System.from_callable(lambda x: x, name="synthetic-identity", revision="r1")
    benchmark = bs.Benchmark(
        "synthetic-export", "r1", values, values,
        lambda a, b: bs.Score(success=a == b, metrics={"error": abs(a-b)}),
        "exact-r1", authoritative=True,
    )
    return bs.pipeline("system-evaluation", system=system, benchmark=benchmark)


def main():
    pipeline = fixture()
    run = pipeline()
    def export():
        return [json.dumps(t.to_dict(), sort_keys=True, allow_nan=False) for t in run.trials]
    def full_path():
        measured = pipeline()
        comparison = bs.compare_system_runs(measured, measured, metrics=("error",))
        assert comparison.valid_binary_pairs == len(measured.trials)
        return [json.dumps(t.to_dict(), sort_keys=True, allow_nan=False) for t in measured.trials]
    exported = export()
    assert len(exported) == 4000
    print("Synthetic 4000-record export; median of 5 runs:", median(repeat(export, number=1, repeat=5)))
    profile = cProfile.Profile()
    profile.runcall(full_path)
    pstats.Stats(profile).strip_dirs().sort_stats("cumulative").print_stats(10)
    print("No model, simulator or GPU. Timings do not measure inference or production throughput.")


if __name__ == "__main__":
    main()
