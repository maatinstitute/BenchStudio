"""Python-first evaluation of callable models, agents and composed systems."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from functools import cached_property
from typing import Any, Callable, Sequence

from .system_spec import Component, SystemSpec, _canonical
from .system_evidence import TrialKey


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


from .evaluation_engine import EvaluationEngine


class SystemEvaluationPipeline(EvaluationEngine):
    """Task-oriented facade of the shared evaluation engine.

    Construction and check() are inert. run()/arun() execute the declared system
    and independent scorer. Backend loading is owned by the System runtime.
    """
