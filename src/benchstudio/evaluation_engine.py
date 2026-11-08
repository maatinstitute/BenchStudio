"""Common evaluation engine for callable systems and persistent execution backends."""
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
    max_retries: int = 0
    continue_on_error: bool = False

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
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries must be a nonnegative integer")
        if type(self.continue_on_error) is not bool:
            raise TypeError("continue_on_error must be boolean")
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

    """Coordinate callable evaluations or case requests to a persistent backend.

    Construction is inert. Calling the pipeline runs user-provided code.
    Exceptions propagate; failed execution is never converted into task failure.
    This sequential runtime does not promise batching or GPU acceleration.
    """
    def __init__(self, *, system=None, benchmark=None, backend=None, config=None, run_id=None):
        from .system_pipeline import System, Benchmark
        if config is not None and not isinstance(config, EvaluationConfig):
            raise TypeError("config must be bs.EvaluationConfig")
        if config is not None and run_id is not None:
            raise ValueError("run_id belongs in config when config is supplied")
        self.config = config or EvaluationConfig(run_id="evaluation" if run_id is None else run_id)
        run_id = self.config.run_id
        self.backend = backend
        if backend is not None:
            if system is not None or benchmark is not None:
                raise ValueError("provide an execution backend or System + Benchmark, not both")
            for method in ("check", "start", "execute_case", "record", "close", "finish"):
                if not callable(getattr(backend, method, None)):
                    raise TypeError("execution backend requires " + method + "()")
            self.cases = tuple(backend.cases)
            if (not self.cases or any(type(case) is not str or not case for case in self.cases)
                    or len(set(self.cases)) != len(self.cases)):
                raise ValueError("backend cases must have unique nonempty string identities")
            self.run_id = run_id
            return
        if not isinstance(system, System) or not isinstance(benchmark, Benchmark):
            raise TypeError("provide a System and a Benchmark")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        self.system, self.benchmark, self.run_id = system, benchmark, run_id

    def check(self, *, mode="sync", batch_size=None):
        if mode not in ("sync", "async"):
            raise ValueError("mode must be sync or async")
        if self.backend is not None:
            issues = list(self.backend.check(self.config))
            if mode != "sync" or self.config.concurrency != 1:
                issues.append("execution backends currently require sequential run()")
            if self.config.batch_size is not None or batch_size is not None:
                issues.append("execution backends do not support model batching")
            if self.config.timeout is not None and getattr(self.backend, "supports_timeout", False) is not True:
                issues.append("backend cannot enforce a timeout safely")
            if self.config.output_dir is not None and self.config.output_dir.exists():
                issues.append("output directory already exists")
            return EvaluationCheck(not issues, tuple(issues), len(self.cases), "backend")
        size = self.config.batch_size if batch_size is None else batch_size
        from .backend_loading import requirement_issues
        issues = requirement_issues(self.system.runtime)
        if self.config.max_retries or self.config.continue_on_error:
            issues.append("retry/continuation settings require an execution backend")
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
        if self.backend is not None:
            check = self.check(batch_size=batch_size)
            if not check.configuration_valid:
                raise ValueError("; ".join(check.issues))
            with self._session() as retain:
                result = self._run_cases()
                retain(result)
                return result
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
        record = {"status": "running", "configuration": config}
        if self.backend is None:
            record.update(system_digest=self.system.spec.digest,
                          benchmark_protocol_digest=self.benchmark.protocol_digest)
        else:
            record.update(backend=type(self.backend).__module__ + "." + type(self.backend).__qualname__,
                          cases=list(self.cases))
        path = output / "execution.json"
        def write():
            path.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
        write()
        saved = False
        def retain(result):
            nonlocal saved
            if self.backend is None:
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
            if self.backend is not None and saved and not self._cases_complete:
                record["status"] = "incomplete"
        finally:
            write()

    def _case_receipt(self, case, attempt, completed, error=None):
        if self.config.output_dir is None:
            return
        record = {"schema": "benchstudio.case_attempt.v1",
                  "case": case, "attempt": attempt, "completed": completed}
        if error is not None:
            record.update(error_type=type(error).__name__, error=str(error))
        with (self.config.output_dir / "cases.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()

    def _run_cases(self):
        self._cases_complete = True
        try:
            # One reusable worker lifecycle per run, independent of request state.
            self.backend.start(self.config)
            self._execute_cases()
        except BaseException as error:
            try:
                self.backend.close()
            except BaseException as cleanup_error:
                raise error from cleanup_error
            raise
        else:
            self.backend.close()
        return self.backend.finish()

    def _execute_cases(self):
        from .backends import CaseResult
        for case in self.cases:
            for attempt in range(1, self.config.max_retries + 2):
                try:
                    result = self.backend.execute_case(case, attempt=attempt, config=self.config)
                    if not isinstance(result, CaseResult):
                        if inspect.iscoroutine(result):
                            result.close()
                        raise TypeError("execute_case() must return benchstudio.backends.CaseResult")
                except BaseException as error:
                    self._case_receipt(case, attempt, False, error)
                    try:
                        self.backend.record(case, CaseResult(False), attempt=attempt)
                    except BaseException as reporting_error:
                        raise error from reporting_error
                    raise
                self._case_receipt(case, attempt, result.completed)
                self.backend.record(case, result, attempt=attempt)
                if result.completed:
                    break
            if not result.completed:
                self._cases_complete = False
                if not self.config.continue_on_error:
                    break

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
