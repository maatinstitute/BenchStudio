"""Python-first evaluation of callable models, agents and composed systems."""
from __future__ import annotations

import asyncio
import inspect
import math
from dataclasses import dataclass
import hashlib
from functools import cached_property
from typing import Any, Callable, Sequence

from .system_spec import Component, SystemSpec, _canonical
from .system_evidence import SystemRun, Trial, TrialKey


@dataclass(frozen=True)
class System:
    """A callable runtime plus its explicitly declared implementation identity.

    The callable may wrap an entire agent workflow. It owns reset/lifecycle
    management; this adapter neither loads weights nor executes a graph.
    """
    runtime: Callable[[Any], Any]
    spec: SystemSpec

    def __post_init__(self):
        if not callable(self.runtime):
            raise TypeError("system runtime must be callable")

    @classmethod
    def from_pretrained(cls, model, *, revision, backend="vllm", generation=None, **options):
        """Configure a supported model backend; loading begins at first execution."""
        if backend != "vllm":
            raise ValueError("supported pretrained backends: vllm")
        from .vllm_backend import GenerationConfig, VLLMConfig, VLLMRuntime
        if generation is not None and not isinstance(generation, GenerationConfig):
            raise TypeError("generation must be bs.GenerationConfig")
        runtime = VLLMRuntime(VLLMConfig(model, revision, **options), generation or GenerationConfig())
        return cls(runtime, runtime.system_spec())

    @classmethod
    def from_callable(cls, runtime, *, name: str, revision: str, kind: str = "system"):
        return cls(runtime, SystemSpec(name, revision, (
            Component("system", kind, name, revision),
        )))


@dataclass(frozen=True)
class Score:
    """An evaluator's task outcome and/or continuous metrics."""
    success: bool | None = None
    metrics: dict[str, float] | None = None


@dataclass(frozen=True)
class Benchmark:
    """An in-memory dataset and independent scorer, with pinned identities.

    Reuse this object for paired comparisons. Revision must identify the
    dataset and scoring definition; these declarations are not attestations.
    """
    name: str
    revision: str
    inputs: Sequence[Any]
    targets: Sequence[Any]
    scorer: Callable[[Any, Any], Score]
    evaluator_revision: str
    environment_revision: str = "offline"
    authoritative: bool = False

    def __post_init__(self):
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "targets", tuple(self.targets))
        if not self.inputs or len(self.inputs) != len(self.targets):
            raise ValueError("benchmark requires equal nonempty inputs and targets")
        if not callable(self.scorer):
            raise TypeError("benchmark scorer must be callable")
        if type(self.authoritative) is not bool:
            raise TypeError("authoritative must be boolean")
        # Validate all identity fields before any runtime call.
        self.key(0)

    @cached_property
    def protocol_digest(self):
        return hashlib.sha256(_canonical({
            "task": self.name, "revision": self.revision,
            "evaluator_revision": self.evaluator_revision,
            "environment_revision": self.environment_revision,
            "design": "ordered-dataset-v1", "cases": len(self.inputs),
        })).hexdigest()

    def key(self, index):
        return TrialKey(self.name, self.revision, str(index), "nominal", 0, 0,
                        self.environment_revision, self.protocol_digest,
                        self.name + "/scorer", self.evaluator_revision)


class SystemEvaluationPipeline:
    """Run a callable on a benchmark, then score its outputs separately.

    Construction is inert. Calling the pipeline runs user-provided code.
    Exceptions propagate; failed execution is never converted into task failure.
    This sequential runtime does not promise batching or GPU acceleration.
    """
    def __init__(self, *, system: System, benchmark: Benchmark, run_id: str = "evaluation"):
        if not isinstance(system, System) or not isinstance(benchmark, Benchmark):
            raise TypeError("provide a System and a Benchmark")
        if not isinstance(run_id, str) or not run_id.strip():
            raise ValueError("run_id must be nonempty")
        self.system, self.benchmark, self.run_id = system, benchmark, run_id

    def __call__(self, *, batch_size=None):
        return self.run(batch_size=batch_size)

    def run(self, *, batch_size=None):
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

    async def arun(self, *, concurrency=1, timeout=None):
        """Evaluate with bounded cooperative workers and stable trial ordering.

        concurrency > 1 requires independent runtime sessions/state per input.
        timeout is per trial including scoring. Cancellation is cooperative;
        this cannot stop blocking Python, remote jobs or native GPU kernels.
        """
        from .async_execution import ordered_map

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
        if not isinstance(score, Score):
            raise TypeError("benchmark scorer must return bs.Score")
        return Trial(str(index), self.benchmark.key(index), self.system.spec.digest,
                     "completed", score.success, "declared", self.benchmark.authoritative,
                     dict(score.metrics or {}))
