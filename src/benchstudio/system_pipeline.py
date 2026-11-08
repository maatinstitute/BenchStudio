"""Python-first evaluation of callable models, agents and composed systems."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from functools import cached_property
from typing import Any, Callable, Sequence, Mapping

from .system_spec import Component, SystemSpec, _canonical, _thaw
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
        """Compatibility loader for supported backends; native configured callables are preferred."""
        if backend != "vllm":
            return cls.from_backend(backend, model=model, revision=revision, generation=generation, **options)
        from .vllm_backend import GenerationConfig, VLLMConfig, VLLMRuntime
        if generation is not None and not isinstance(generation, GenerationConfig):
            raise TypeError("generation must be bs.GenerationConfig")
        runtime = VLLMRuntime(VLLMConfig(model, revision, **options), generation or GenerationConfig())
        return cls(runtime, runtime.system_spec())

    @classmethod
    def from_backend(cls, name, **options):
        """Resolve a trusted installed system factory, with no source-file arguments."""
        if name == "vllm":
            return cls.from_pretrained(**options)
        from .backend_loading import load_backend
        result = load_backend("benchstudio.systems", name)(**options)
        if not isinstance(result, cls):
            raise TypeError("system backend factory must return bs.System")
        if "revision" in options and result.spec.revision != options["revision"]:
            raise ValueError("system factory returned a different revision")
        return result

    @classmethod
    def from_callable(cls, runtime, *, name: str, revision: str, kind: str = "system",
                      batched: bool = False, configuration: Mapping[str, Any] | None = None,
                      dependencies: Sequence[str] = ()):
        """Bind an already configured native function without choosing model settings.

        batched=True accepts one native output per input. configuration is a
        user-declared provenance snapshot, not an inference-parameter schema.
        Native objects stay in the callable/partial, never in a mirrored config.
        """
        import inspect
        from importlib import metadata
        if not callable(runtime):
            raise TypeError("system runtime must be callable")
        if type(batched) is not bool:
            raise TypeError("batched must be boolean")
        if configuration is not None and not isinstance(configuration, Mapping):
            raise TypeError("configuration must be an explicit provenance mapping")
        if isinstance(dependencies, str):
            raise TypeError("dependencies must be a sequence of distribution names")
        dependencies = tuple(dependencies)
        if any(type(value) is not str or not value.strip() for value in dependencies):
            raise ValueError("dependency distribution names must be nonempty")
        versions = {distribution: metadata.version(distribution) for distribution in dependencies}
        details = {}
        if batched or configuration is not None or dependencies:
            from .callables import DeclaredCallable, BatchedCallable
            target = inspect.unwrap(runtime)
            if batched and (inspect.iscoroutinefunction(target) or inspect.iscoroutinefunction(
                    getattr(target, "__call__", None))):
                raise TypeError("batched callables must be synchronous")
            details = {
                "callable": {"batched": batched},
                "configuration": {"status": "opaque"} if configuration is None else {
                    "status": "declared", "values": _thaw(configuration)},
                "distributions": versions,
            }
            runtime = (BatchedCallable if batched else DeclaredCallable)(runtime, configuration)
        return cls(runtime, SystemSpec(name, revision, (
            Component("system", kind, name, revision),
        ), metadata=details))

    def describe(self):
        """Inspect declared identity/configuration without executing the runtime."""
        details = self.spec.to_dict()["metadata"]
        return {
            "name": self.spec.system_id, "revision": self.spec.revision,
            "configuration": details.get("configuration", {"status": "opaque"}),
            "distributions": details.get("distributions", {}),
            "batched": details.get("callable", {}).get("batched", False),
            "system_digest": self.spec.digest, "metadata": details,
        }


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

    @classmethod
    def load(cls, name, *, revision, **options):
        """Load a trusted installed benchmark recipe with pinned dataset/scorer identity."""
        from .backend_loading import load_backend
        result = load_backend("benchstudio.benchmarks", name)(revision=revision, **options)
        if not isinstance(result, cls):
            raise TypeError("benchmark factory must return bs.Benchmark")
        if result.revision != revision:
            raise ValueError("benchmark factory returned a different revision")
        return result

    @classmethod
    def from_pretrained(cls, name, *, revision, **options):
        """Compatibility alias for Benchmark.load()."""
        return cls.load(name, revision=revision, **options)

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
