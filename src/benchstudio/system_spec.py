"""Immutable, runtime-independent specifications for composed AI systems.

A system is a graph, not a single Policy. Nodes can be VLAs, world models,
world-action models, planning tools, multiple agents, simulators or evaluators.
Graph cycles (feedback) and disconnected parallel branches are intentional.
This module does not execute any graph.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
from functools import cached_property
import json
import re
from types import MappingProxyType
from typing import Any, Mapping


def _name(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("system metadata must be canonical JSON") from exc


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value):
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class Component:
    component_id: str
    kind: str
    implementation: str
    revision: str
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    config_digest: str | None = None

    def __post_init__(self) -> None:
        for label in ("component_id", "kind", "implementation", "revision"):
            _name(getattr(self, label), label)
        for label in ("inputs", "outputs"):
            ports = getattr(self, label)
            if not isinstance(ports, tuple) or any(
                not isinstance(p, str) or not p.strip() for p in ports
            ) or len(ports) != len(set(ports)):
                raise ValueError(f"{label} must be unique nonempty port names")
        if self.config_digest is not None and not re.fullmatch(
            r"[0-9a-f]{64}", self.config_digest
        ):
            raise ValueError("config_digest must be lowercase SHA-256")


@dataclass(frozen=True)
class Connection:
    source: str
    source_port: str
    target: str
    target_port: str

    def __post_init__(self) -> None:
        for label in ("source", "source_port", "target", "target_port"):
            _name(getattr(self, label), label)


@dataclass(frozen=True)
class SystemSpec:
    system_id: str
    revision: str
    components: tuple[Component, ...]
    connections: tuple[Connection, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _name(self.system_id, "system_id")
        _name(self.revision, "revision")
        if not isinstance(self.components, tuple) or not self.components:
            raise ValueError("system requires one or more components")
        if not isinstance(self.connections, tuple):
            raise ValueError("connections must be a tuple")
        ids = [c.component_id for c in self.components]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate component_id")
        nodes = {c.component_id: c for c in self.components}
        if len(self.connections) != len(set(self.connections)):
            raise ValueError("duplicate graph connection")
        for edge in self.connections:
            if edge.source not in nodes or edge.target not in nodes:
                raise ValueError("connection references unknown component")
            if edge.source_port not in nodes[edge.source].outputs:
                raise ValueError("connection references unknown output port")
            if edge.target_port not in nodes[edge.target].inputs:
                raise ValueError("connection references unknown input port")
        if not isinstance(self.metadata, Mapping):
            raise ValueError("metadata must be a JSON mapping")
        object.__setattr__(self, "metadata", _freeze(json.loads(_canonical(dict(self.metadata)))))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "benchstudio.system.v1",
            "system_id": self.system_id,
            "revision": self.revision,
            "components": [asdict(c) for c in self.components],
            "connections": [asdict(e) for e in self.connections],
            "metadata": _thaw(self.metadata),
        }

    @cached_property
    def digest(self) -> str:
        return hashlib.sha256(_canonical(self.to_dict())).hexdigest()

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SystemSpec":
        if not isinstance(value, Mapping) or value.get("schema") != "benchstudio.system.v1":
            raise ValueError("unsupported system schema")
        if set(value) - {
            "schema", "system_id", "revision", "components", "connections", "metadata"
        }:
            raise ValueError("unknown system spec fields")
        return cls(
            system_id=value["system_id"], revision=value["revision"],
            components=tuple(Component(
                **{**item, "inputs": tuple(item.get("inputs", ())),
                   "outputs": tuple(item.get("outputs", ()))}
            ) for item in value["components"]),
            connections=tuple(Connection(**item) for item in value.get("connections", [])),
            metadata=value.get("metadata", {}),
        )

