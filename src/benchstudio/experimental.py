"""Executable ordered workflows and declared paired component interventions."""
from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Mapping

from .async_execution import invoke, ordered_map
from .system_ablations import AblationAudit, audit_ablation
from .system_comparison import SystemComparison, compare_system_runs
from .system_evidence import SystemRun
from .evaluation_engine import EvaluationConfig
from .system_pipeline import Benchmark, System, SystemEvaluationPipeline
from .system_spec import Component, Connection, SystemSpec


@dataclass(frozen=True, init=False)
class Workflow:
    """An ordered composition of callable systems, using output-to-input flow.

    Each stage receives the preceding stage's output. An AgentGroup can be a
    stage. This is not an arbitrary graph/feedback interpreter. Stage runtimes
    own state, external permissions and cleanup.
    """
    stages: Mapping[str, System]
    spec: SystemSpec

    def __init__(self, name: str, revision: str, stages: Mapping[str, System]):
        if not stages or any(not isinstance(s, System) for s in stages.values()):
            raise TypeError("stages must be a nonempty mapping of System objects")
        object.__setattr__(self, "stages", MappingProxyType(dict(stages)))
        nodes = tuple(Component(key, "system", value.spec.system_id,
                                value.spec.revision, inputs=("value",), outputs=("value",),
                                config_digest=value.spec.digest)
                      for key, value in self.stages.items())
        names = tuple(self.stages)
        edges = tuple(Connection(a, "value", b, "value") for a, b in zip(names, names[1:]))
        object.__setattr__(self, "spec", SystemSpec(name, revision, nodes, edges))

    def replace(self, component: str, system: System, *, revision: str):
        if component not in self.stages:
            raise ValueError("unknown workflow component")
        stages = dict(self.stages)
        stages[component] = system
        return Workflow(self.spec.system_id, revision, stages)

    async def __call__(self, value):
        for stage in self.stages.values():
            value = await invoke(stage.runtime, value)
        return value

    def as_system(self):
        return System(self, self.spec)


@dataclass(frozen=True)
class AblationResult:
    reference: SystemRun
    candidate: SystemRun
    isolation: AblationAudit
    comparison: SystemComparison
    arm_order: tuple[tuple[str, str], ...]

    def summary(self):
        return {
            "declared_change_isolated": self.isolation.structurally_isolated,
            "matched_binary_pairs": self.comparison.valid_binary_pairs,
            "incomplete_binary_pairs": self.comparison.incomplete_pairs,
            "success_delta": self.comparison.paired_success.success_gap_b_minus_a,
            "numeric_deltas": {d.name: d.mean_b_minus_a for d in self.comparison.numeric_deltas},
            "interpretation": self.comparison.interpretation,
        }


class AblationStudy:
    """Run two declared variants on the same benchmark with paired arm order.

    Each pair alternates AB/BA by index; this is recorded, not randomized.
    Input/target copies prevent ordinary in-memory mutation crossing arms.
    Copies do not reset model state, RNGs, tools or environments. Runtimes must
    provide those guarantees. Exceptions abort without partial-run persistence.
    """
    def __init__(self, *, reference: System, candidate: System, benchmark: Benchmark,
                 changed_components: tuple[str, ...], metrics=(), clone_input=copy.deepcopy):
        self.reference = SystemEvaluationPipeline(system=reference, benchmark=benchmark,
            config=EvaluationConfig(run_id="reference"))
        self.candidate = SystemEvaluationPipeline(system=candidate, benchmark=benchmark,
            config=EvaluationConfig(run_id="candidate"))
        self.isolation = audit_ablation(reference.spec, candidate.spec,
                                        allowed_components=changed_components)
        if not self.isolation.structurally_isolated:
            raise ValueError("intervention is not isolated: " + "; ".join(self.isolation.issues))
        self.metrics = tuple(metrics)
        # Validate analysis arguments before runtime execution.
        compare_system_runs(SystemRun("reference", reference.spec, ()),
                            SystemRun("candidate", candidate.spec, ()), metrics=self.metrics)
        if not callable(clone_input):
            raise TypeError("clone_input must be callable")
        self.clone_input = clone_input
        self.benchmark = benchmark

    async def arun(self, *, concurrency=1, timeout=None):
        if timeout is not None and (type(timeout) not in (int, float) or
                                    not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be finite and positive")
        async def pair(index):
            # Prepare both arm inputs before executing either arm.
            inputs = [self.clone_input(self.benchmark.inputs[index]) for _ in range(2)]
            targets = [copy.deepcopy(self.benchmark.targets[index]) for _ in range(2)]
            order = (0, 1) if index % 2 == 0 else (1, 0)
            pipelines = (self.reference, self.candidate)
            records = [None, None]
            for arm in order:
                work = pipelines[arm]._evaluate_trial(index, inputs[arm], targets[arm])
                records[arm] = await work if timeout is None else await asyncio.wait_for(work, timeout)
            return records
        rows = await ordered_map(pair, range(len(self.benchmark.inputs)), concurrency=concurrency)
        reference = SystemRun("reference", self.reference.system.spec, tuple(row[0] for row in rows))
        candidate = SystemRun("candidate", self.candidate.system.spec, tuple(row[1] for row in rows))
        order = tuple(("reference", "candidate") if i % 2 == 0 else ("candidate", "reference")
                      for i in range(len(rows)))
        return AblationResult(reference, candidate, self.isolation,
                              compare_system_runs(reference, candidate, metrics=self.metrics), order)
