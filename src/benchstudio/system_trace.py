"""Causal/temporal trace audit for composed AI-system evaluations.

Descriptive auditing only: observed event lineage does not prove a causal
effect, clock synchronization or an unlogged interaction.
"""
from __future__ import annotations
from dataclasses import dataclass
import re

from .system_spec import Connection, SystemSpec


@dataclass(frozen=True)
class SystemEvent:
    trial_id: str
    event_id: str
    component_id: str
    kind: str
    time_ns: int
    clock_domain: str
    parent_event_id: str | None = None
    input_port: str | None = None
    output_port: str | None = None
    payload_digest: str | None = None

    def __post_init__(self) -> None:
        for name in ("trial_id", "event_id", "component_id", "kind", "clock_domain"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonempty")
        if type(self.time_ns) is not int or self.time_ns < 0:
            raise ValueError("time_ns must be nonnegative integer")
        if self.payload_digest is not None and re.fullmatch(
            "[0-9a-f]{64}", self.payload_digest
        ) is None:
            raise ValueError("payload_digest must be lowercase SHA-256")


@dataclass(frozen=True)
class TraceAudit:
    valid: bool
    events: int
    observed_connections: tuple[Connection, ...]
    unobserved_connections: tuple[Connection, ...]
    issues: tuple[str, ...]
    clock_domains: tuple[str, ...]


def audit_system_trace(system: SystemSpec, events: list[SystemEvent] | tuple[SystemEvent, ...]) -> TraceAudit:
    """Validate event references, port-level communication and clock provenance.

    Event parent links may cross components only along declared SystemSpec
    edges, with matching output and input ports. Across clock domains no
    timestamp ordering is inferred. Intra-domain ordering is checked.
    """
    nodes = {component.component_id: component for component in system.components}
    connections = {(e.source, e.source_port, e.target, e.target_port): e
                   for e in system.connections}
    ids: dict[str, SystemEvent] = {}
    issues: list[str] = []
    observed: set[Connection] = set()
    for event in events:
        if event.event_id in ids:
            issues.append(f"duplicate event_id: {event.event_id}")
        ids[event.event_id] = event
        component = nodes.get(event.component_id)
        if component is None:
            issues.append(f"{event.event_id}: unknown component {event.component_id}")
            continue
        if event.input_port is not None and event.input_port not in component.inputs:
            issues.append(f"{event.event_id}: undeclared input port")
        if event.output_port is not None and event.output_port not in component.outputs:
            issues.append(f"{event.event_id}: undeclared output port")
    for event in events:
        if event.parent_event_id is None:
            continue
        parent = ids.get(event.parent_event_id)
        if parent is None:
            issues.append(f"{event.event_id}: missing parent event")
            continue
        if parent.trial_id != event.trial_id:
            issues.append(f"{event.event_id}: parent belongs to a different trial")
            continue
        if parent.clock_domain == event.clock_domain and parent.time_ns > event.time_ns:
            issues.append(f"{event.event_id}: timestamp precedes parent")
        if parent.component_id != event.component_id:
            if parent.output_port is None or event.input_port is None:
                issues.append(f"{event.event_id}: cross-component link needs explicit ports")
                continue
            edge = connections.get((parent.component_id, parent.output_port,
                                    event.component_id, event.input_port))
            if edge is None:
                issues.append(f"{event.event_id}: undeclared cross-component connection")
            else:
                observed.add(edge)
    # Event lineage is acyclic even when the component graph has feedback.
    checked = set()
    for event_id in ids:
        chain = set()
        current = event_id
        while current in ids and current not in checked:
            if current in chain:
                issues.append(f"{current}: cyclic parent lineage")
                break
            chain.add(current)
            current = ids[current].parent_event_id
        checked.update(chain)
    return TraceAudit(
        valid=not issues, events=len(events),
        observed_connections=tuple(e for e in system.connections if e in observed),
        unobserved_connections=tuple(e for e in system.connections if e not in observed),
        issues=tuple(issues),
        clock_domains=tuple(sorted({e.clock_domain for e in events})),
    )

