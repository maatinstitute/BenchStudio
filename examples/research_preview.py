"""Installed-package smoke: real arithmetic, no model or environment dependencies."""
from pathlib import Path
import sys
import benchstudio as bs


def main(output):
    system = bs.System.from_callable(lambda x: 2*x, name="double", revision="r1")
    benchmark = bs.Benchmark("arithmetic", "r1", [1, 2], [2, 4],
        lambda value, target: bs.Score(success=value == target,
                                      metrics={"absolute_error": abs(value-target)}), "exact-r1")
    evaluation = bs.pipeline(system=system, benchmark=benchmark,
        config=bs.EvaluationConfig(output_dir=output))
    assert evaluation.check().configuration_valid
    assert not evaluation.capabilities["batching"]
    native = evaluation()
    report = evaluation.report()
    assert report.native is native and not report.coverage.missing
    assert all(t.success is True for t in native.trials)
    assert all(not t.authoritative for t in native.trials)
    saved = bs.inspect_result(bs.open_run(output))
    assert saved.coverage == report.coverage and saved.metrics == report.metrics
    assert report.summary() == saved.summary()
    print(report.summary())


if __name__ == "__main__":
    main(Path(sys.argv[1]))
