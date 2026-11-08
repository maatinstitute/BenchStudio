"""Shared evaluation configuration and execution for callable system backends."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import inspect
import math

from .system_evidence import SystemRun, Trial


@dataclass(frozen=True)
class EvaluationConfig:
    """Execution settings shared by the engine and system pipeline.

    Backend/model settings remain on System; dataset/evaluator settings remain on
    Benchmark. This configuration does not attest native reproducibility.
    """
    run_id: str = "evaluation"
    batch_size: int | None = None
    concurrency: int = 1
    timeout: float | None = None

    def __post_init__(self):
        if not isinstance(self.run_id, str) or not self.run_id.strip():
            raise ValueError("run_id must be nonempty")
        for name in ("batch_size", "concurrency"):
            value = getattr(self, name)
            if value is None and name == "batch_size":
                continue
            if type(value) is not int or value < 1:
                raise ValueError(name + " must be a positive integer")
        if self.timeout is not None and (type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or self.timeout <= 0):
            raise ValueError("timeout must be finite and positive")


@dataclass(frozen=True)
class EvaluationCheck:
    """Static compatibility only; no model load, runtime call or qualification."""
    configuration_valid: bool
    issues: tuple[str, ...]
    cases: int
    mode: str
    native_verified: bool = False


class EvaluationEngine:

    """Run a callable on a benchmark, then score its outputs separately.

    Construction is inert. Calling the pipeline runs user-provided code.
    Exceptions propagate; failed execution is never converted into task failure.
    This sequential runtime does not promise batching or GPU acceleration.
    """
    def __init__(self, *, system, benchmark, config=None, run_id=None):
        from .system_pipeline import System, Benchmark
        if config is not None and not isinstance(config, EvaluationConfig):
            raise TypeError("config must be bs.EvaluationConfig")
        if config is not None and run_id is not None:
            raise ValueError("run_id belongs in config when config is supplied")
        self.config = config or EvaluationConfig(run_id="evaluation" if run_id is None else run_id)
        run_id = self.config.run_id
        if not isinstance(system, System) or not isinstance(benchmark, Benchmark):
            raise TypeError("provide a System and a Benchmark")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        self.system, self.benchmark, self.run_id = system, benchmark, run_id

    def check(self, *, mode="sync", batch_size=None):
        if mode not in ("sync", "async"):
            raise ValueError("mode must be sync or async")
        size = self.config.batch_size if batch_size is None else batch_size
        issues = []
        if size is not None and (type(size) is not int or size < 1):
            issues.append("batch_size must be a positive integer")
        if mode == "sync":
            if self.config.concurrency != 1 or self.config.timeout is not None:
                issues.append("concurrency/timeout require arun(); synchronous calls cannot be interrupted safely")
            if size is not None and not callable(getattr(self.system.runtime, "generate_batch", None)):
                issues.append("system runtime does not support generate_batch")
            if inspect.iscoroutinefunction(self.system.runtime) or inspect.iscoroutinefunction(
                    getattr(self.system.runtime, "__call__", None)):
                issues.append("async runtimes require arun()")
        elif size is not None:
            issues.append("async batching is not supported; use run() or remove batch_size")
        return EvaluationCheck(not issues, tuple(issues), len(self.benchmark.inputs), mode)

    def __call__(self, *, batch_size=None):
        return self.run(batch_size=batch_size)

    def run(self, *, batch_size=None):
        if self.config.concurrency != 1 or self.config.timeout is not None:
            raise ValueError("concurrency/timeout require arun()")
        batch_size = self.config.batch_size if batch_size is None else batch_size
        if batch_size is not None:
            return self._run_batches(batch_size)
        trials = []
        for index, (inputs, target) in enumerate(zip(self.benchmark.inputs, self.benchmark.targets)):
            output = self.system.runtime(inputs)
            if inspect.isawaitable(output):
                if inspect.iscoroutine(output):
                    output.close()
                raise TypeError("async runtimes require await pipeline.arun()")
            score = self.benchmark.scorer(output, target)
            if inspect.isawaitable(score):
                if inspect.iscoroutine(score):
                    score.close()
                raise TypeError("async scorers require await pipeline.arun()")
            trials.append(self._record_trial(index, score))
        return SystemRun(self.run_id, self.system.spec, tuple(trials))

    def _run_batches(self, batch_size):
        if type(batch_size) is not int or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")
        generate = getattr(self.system.runtime, "generate_batch", None)
        if not callable(generate):
            raise TypeError("system runtime does not support generate_batch")
        trials = []
        for start in range(0, len(self.benchmark.inputs), batch_size):
            inputs = self.benchmark.inputs[start:start + batch_size]
            outputs = list(generate(inputs))
            if len(outputs) != len(inputs):
                raise ValueError("batch output count differs from input count")
            for offset, output in enumerate(outputs):
                index = start + offset
                score = self.benchmark.scorer(output, self.benchmark.targets[index])
                if inspect.isawaitable(score):
                    if inspect.iscoroutine(score):
                        score.close()
                    raise TypeError("batch scoring must be synchronous")
                trials.append(self._record_trial(index, score))
        return SystemRun(self.run_id, self.system.spec, tuple(trials))

    async def arun(self, *, concurrency=None, timeout=None):
        """Evaluate with bounded cooperative workers and stable trial ordering.

        concurrency > 1 requires independent runtime sessions/state per input.
        timeout is per trial including scoring. Cancellation is cooperative;
        this cannot stop blocking Python, remote jobs or native GPU kernels.
        """
        from .async_execution import ordered_map

        if self.config.batch_size is not None:
            raise ValueError("async batching is not supported; use run() or remove batch_size")
        concurrency = self.config.concurrency if concurrency is None else concurrency
        timeout = self.config.timeout if timeout is None else timeout

        if timeout is not None and (type(timeout) not in (int, float) or
                                    not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        async def evaluate(index):
            work = self._evaluate_trial(index, self.benchmark.inputs[index],
                                        self.benchmark.targets[index])
            return await work if timeout is None else await asyncio.wait_for(work, timeout)
        trials = await ordered_map(evaluate, range(len(self.benchmark.inputs)), concurrency=concurrency)
        return SystemRun(self.run_id, self.system.spec, tuple(trials))

    async def _evaluate_trial(self, index, inputs, target):
        from .async_execution import invoke
        output = await invoke(self.system.runtime, inputs)
        score = await invoke(lambda value: self.benchmark.scorer(value, target), output)
        return self._record_trial(index, score)

    def _record_trial(self, index, score):
        from .system_pipeline import Score
        if not isinstance(score, Score):
            raise TypeError("benchmark scorer must return bs.Score")
        return Trial(str(index), self.benchmark.key(index), self.system.spec.digest,
                     "completed", score.success, "declared", self.benchmark.authoritative,
                     dict(score.metrics or {}))
