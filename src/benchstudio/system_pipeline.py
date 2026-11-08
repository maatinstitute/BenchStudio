"""Python-first evaluation of callable models, agents and composed systems."""
from __future__ import annotations

from dataclasses import dataclass, field
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
    """An offline dataset/scorer or a complete executable native protocol.

    Protocol mode owns its experimental calendar, native execution and outcome
    semantics. Offline identities remain compatible. Declared revisions and
    calendar hashes are not native qualification or execution authorization.
    """
    name: str
    revision: str
    inputs: Sequence[Any] = ()
    targets: Sequence[Any] = ()
    scorer: Callable[[Any, Any], Score] | None = None
    evaluator_revision: str | None = None
    environment_revision: str = "offline"
    authoritative: bool = False
    protocol: Any = field(default=None, repr=False, compare=False)
    _cases: tuple = field(default=(), init=False, repr=False)
    _supports_retries: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "inputs", tuple(self.inputs))
        object.__setattr__(self, "targets", tuple(self.targets))
        if self.protocol is not None:
            from .backends import BenchmarkCase
            if self.inputs or self.targets or self.scorer is not None:
                raise ValueError("provide an executable protocol or offline inputs/targets/scorer, not both")
            if not callable(getattr(self.protocol, "bind", None)):
                raise TypeError("benchmark protocol requires bind()")
            cases = tuple(self.protocol.cases)
            if not cases or any(not isinstance(case, BenchmarkCase) for case in cases):
                raise ValueError("protocol cases must be a nonempty sequence of BenchmarkCase")
            if len({case.case_id for case in cases}) != len(cases):
                raise ValueError("duplicate benchmark case identity")
            for label in ("name", "revision", "evaluator_revision", "environment_revision"):
                if not isinstance(getattr(self, label), str) or not getattr(self, label).strip():
                    raise ValueError(label + " must be nonempty")
            if self.environment_revision == "offline":
                raise ValueError("an executable protocol must declare its execution environment revision")
            if type(self.authoritative) is not bool:
                raise TypeError("authoritative must be boolean")
            if self.authoritative:
                raise ValueError("protocol outcome authority belongs to the native evaluator")
            retryable = getattr(self.protocol, "supports_retries", False)
            if type(retryable) is not bool:
                raise TypeError("protocol supports_retries must be boolean")
            object.__setattr__(self, "_cases", cases)
            object.__setattr__(self, "_supports_retries", retryable)
            return
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

    @property
    def cases(self):
        """Frozen experimental units, supplied by an executable protocol."""
        return self._cases

    @property
    def supports_retries(self):
        return self._supports_retries

    @cached_property
    def execution_groups(self):
        from types import MappingProxyType
        groups = {}
        for case in self._cases:
            groups.setdefault(case.execution_id, []).append(case.case_id)
        return MappingProxyType({execution: tuple(units) for execution, units in groups.items()})

    @property
    def execution_ids(self):
        return tuple(self.execution_groups)

    def describe(self):
        return {"schema": "benchstudio.benchmark.v1", "name": self.name, "revision": self.revision,
                "mode": "protocol" if self.protocol is not None else "offline",
                "evaluator_revision": self.evaluator_revision, "environment_revision": self.environment_revision,
                "protocol_digest": self.protocol_digest,
                "case_count": len(self._cases) if self.protocol is not None else len(self.inputs),
                "execution_ids": list(self.execution_ids), "supports_retries": self._supports_retries,
                "cases": [case.to_dict() for case in self._cases]}

    @cached_property
    def protocol_digest(self):
        if self.protocol is not None:
            return hashlib.sha256(_canonical({
                "task": self.name, "revision": self.revision,
                "evaluator_revision": self.evaluator_revision, "environment_revision": self.environment_revision,
                "design": "native-protocol-v1", "supports_retries": self._supports_retries, "cases": [case.to_dict() for case in self._cases],
            })).hexdigest()
        return hashlib.sha256(_canonical({
            "task": self.name, "revision": self.revision,
            "evaluator_revision": self.evaluator_revision,
            "environment_revision": self.environment_revision,
            "design": "ordered-dataset-v1", "cases": len(self.inputs),
        })).hexdigest()

    def key(self, index):
        if self.protocol is not None:
            raise TypeError("protocol outcomes retain their native identities; they are not offline scorer rows")
        return TrialKey(self.name, self.revision, str(index), "nominal", 0, 0,
                        self.environment_revision, self.protocol_digest,
                        self.name + "/scorer", self.evaluator_revision)


from .evaluation_engine import EvaluationEngine


class SystemEvaluationPipeline(EvaluationEngine):
    """Task-oriented facade of the shared evaluation engine.

    Construction and check() are inert. Offline mode executes the declared
    callable/scorer; executable benchmarks bind their native protocol instead.
    Both paths use the existing engine and retain their own outcome semantics.
    """
