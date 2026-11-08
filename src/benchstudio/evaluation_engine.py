"""Shared evaluation configuration and execution for callable system backends."""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import inspect
import math
import json
from pathlib import Path
from contextlib import contextmanager

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
    output_dir: str | Path | None = None

    def __post_init__(self):
        if self.output_dir is not None:
            object.__setattr__(self, "output_dir", Path(self.output_dir).resolve())
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

    @property
    def technical_ready(self):
        """Compatibility for installed recipes; configuration is not qualification."""
        return self.configuration_valid

    def summary(self):
        if self.issues:
            return "\n".join(self.issues)
        return (f"Configuration ready: {self.cases} cases ({self.mode}). "
                "Native execution and scientific qualification remain unverified.")


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
        from .backend_loading import requirement_issues
        issues = requirement_issues(self.system.runtime)
        if size is not None and (type(size) is not int or size < 1):
            issues.append("batch_size must be a positive integer")
        if mode == "sync":
            if self.config.concurrency != 1 or self.config.timeout is not None:
                issues.append("concurrency/timeout require arun(); synchronous calls cannot be interrupted safely")
            if size is not None and not callable(getattr(self.system.runtime, "generate_batch", None)):
                issues.append("system runtime does not support generate_batch")
            if inspect.iscoroutinefunction(self.benchmark.scorer) or inspect.iscoroutinefunction(
                    getattr(self.benchmark.scorer, "__call__", None)):
                issues.append("async scorers require arun()")
            if inspect.iscoroutinefunction(self.system.runtime) or inspect.iscoroutinefunction(
                    getattr(self.system.runtime, "__call__", None)):
                issues.append("async runtimes require arun()")
        else:
            if size is not None:
                issues.append("async batching is not supported; use run() or remove batch_size")
            if getattr(self.system.runtime, "supports_async", True) is False:
                issues.append("this backend requires synchronous run()")
        return EvaluationCheck(not issues, tuple(issues), len(self.benchmark.inputs), mode)

    def __call__(self, *, batch_size=None):
        return self.run(batch_size=batch_size)

    def run(self, *, batch_size=None):
        if self.config.concurrency != 1 or self.config.timeout is not None:
            raise ValueError("concurrency/timeout require arun()")
        size = self.config.batch_size if batch_size is None else batch_size
        if size is not None and (type(size) is not int or size < 1):
            raise ValueError("batch_size must be a positive integer")
        check = self.check(batch_size=batch_size)
        if not check.configuration_valid:
            raise TypeError("; ".join(check.issues))
        with self._session() as retain:
            result = self._run(batch_size=batch_size)
            retain(result)
            return result

    @contextmanager
    def _session(self):
        output = self.config.output_dir
        if output is None:
            yield lambda result: None
            return
        # Reserve output before calling any system, scorer or model loader.
        output.mkdir(parents=True, exist_ok=False)
        config = asdict(self.config)
        config["output_dir"] = str(output)
        record = {"status": "running", "configuration": config,
                  "system_digest": self.system.spec.digest,
                  "benchmark_protocol_digest": self.benchmark.protocol_digest}
        path = output / "execution.json"
        def write():
            path.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
        write()
        saved = False
        def retain(result):
            nonlocal saved
            from .system_evidence import _write_run
            _write_run(result, output)
            saved = True
        try:
            yield retain
        except BaseException as error:
            record.update(status="execution_failed", error_type=type(error).__name__, error=str(error))
            raise
        else:
            record["status"] = "completed" if saved else "execution_failed"
        finally:
            write()

    def _run(self, *, batch_size=None):
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
        check = self.check(mode="async")
        if not check.configuration_valid:
            raise ValueError("; ".join(check.issues))
        with self._session() as retain:
            result = await self._arun(concurrency=concurrency, timeout=timeout)
            retain(result)
            return result

    async def _arun(self, *, concurrency=None, timeout=None):
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
