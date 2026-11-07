"""CPU-only evaluation/comparison/result-export profile on synthetic scalar data."""
import cProfile
import json
import pstats
from statistics import median
from timeit import repeat
from time import perf_counter

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
    # Compare the same SHA-format validator with/without memoization, holding
    # its regex/type behavior constant. Each call constructs a fresh benchmark.
    from unittest.mock import patch
    import hashlib
    import benchstudio.system_evidence as evidence
    validator = evidence._validated_sha
    def fresh_path():
        measured = fixture()()
        bs.compare_system_runs(measured, measured, metrics=("error",))
        data = "\n".join(json.dumps(t.to_dict(), sort_keys=True, allow_nan=False) for t in measured.trials)
        return hashlib.sha256(data.encode()).hexdigest()
    variants = (("uncached format validation", validator.__wrapped__),
                ("bounded format-validation cache", validator))
    samples = {label: [] for label, _ in variants}
    digests = set()
    # Alternate order to reduce warm-up/order bias; include cold cache setup.
    for iteration in range(30):
        for label, function in (variants if iteration % 2 == 0 else variants[::-1]):
            validator.cache_clear()
            with patch.object(evidence, "_validated_sha", function):
                start = perf_counter()
                digests.add(fresh_path())
                samples[label].append(perf_counter() - start)
    assert len(digests) == 1
    timings = {label: median(values) for label, values in samples.items()}
    print("Fresh full-path medians (30 alternating samples each):", timings)
    print("Identical complete output digest:", digests.pop())
    print("No model, simulator or GPU. Timings do not measure inference or production throughput.")


if __name__ == "__main__":
    main()
