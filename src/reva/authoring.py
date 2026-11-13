"""Small Python authoring helpers that compile into frozen campaign plans."""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .campaigns.frozen_plan import FrozenCampaignPlan
from .campaigns.spec import compile_campaign_spec


def condition_grid(
    *,
    fixed: Mapping[str, Any] | None = None,
    **factors: Iterable[Any],
) -> tuple[dict[str, Any], ...]:
    """Build a deterministic Cartesian grid of named condition controls.

    The returned mappings remain drafts. They acquire immutable identities only
    when a :class:`PairedStudy` is compiled into a frozen campaign plan.
    """
    if not factors:
        raise ValueError("condition_grid requires at least one factor")
    base = dict(fixed or {})
    overlap = set(base) & set(factors)
    if overlap:
        raise ValueError("fixed controls overlap factors: " + ", ".join(sorted(overlap)))
    if "id" in base:
        raise ValueError("condition_grid generates condition ids; fixed must not contain id")

    names: list[str] = []
    levels: list[tuple[Any, ...]] = []
    for name, values in factors.items():
        if not isinstance(name, str) or not name:
            raise ValueError("factor names must be non-empty strings")
        if isinstance(values, (str, bytes, Mapping)):
            raise ValueError(f"factor {name} must be an iterable of levels")
        level_values = tuple(values)
        if not level_values:
            raise ValueError(f"factor {name} must contain at least one level")
        names.append(name)
        levels.append(level_values)

    conditions: list[dict[str, Any]] = []
    for combination in itertools.product(*levels):
        varied = dict(zip(names, combination))
        condition = {
            **base,
            **varied,
            "id": ",".join(f"{name}={varied[name]}" for name in names),
        }
        try:
            json.dumps(condition, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("condition controls must be JSON serializable") from exc
        conditions.append(condition)
    return tuple(conditions)


def simulator_environment(
    environment_id: str,
    *,
    adapter: str | None = None,
    adapter_config: Mapping[str, Any] | None = None,
    required_capabilities: Mapping[str, bool] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    """Declare a simulator without granting any physical execution authority."""
    environment: dict[str, Any] = {
        "id": environment_id,
        "kind": "simulator",
        "enabled": enabled,
    }
    if adapter is not None:
        environment["adapter"] = adapter
    if adapter_config is not None:
        environment["adapter_config"] = copy.deepcopy(dict(adapter_config))
    if required_capabilities is not None:
        environment["required_capabilities"] = dict(required_capabilities)
    return environment


@dataclass(frozen=True)
class PairedStudy:
    """Author a paired study and compile it through the strict campaign compiler.

    This class does not run models or simulators. ``freeze`` produces the same
    digest-bound :class:`FrozenCampaignPlan` as a hand-written campaign mapping.
    """

    name: str
    task_id: str
    conditions: tuple[Mapping[str, Any], ...]
    seeds: tuple[int, ...]
    environments: tuple[Mapping[str, Any], ...] = field(
        default_factory=lambda: ({"id": "default", "kind": "simulator"},)
    )
    repetitions: int = 1
    protocol_revision: str | None = None
    task: Mapping[str, Any] = field(default_factory=dict)
    model: Mapping[str, Any] = field(default_factory=dict)
    execution: Mapping[str, Any] = field(default_factory=dict)
    measurement: Mapping[str, bool] = field(default_factory=dict)
    outputs: Mapping[str, bool] = field(default_factory=dict)
    resource_budget: Mapping[str, int | float] = field(default_factory=dict)
    evaluation_options: Mapping[str, Any] = field(default_factory=dict)

    def to_spec(self) -> dict[str, Any]:
        """Return the canonical declarative mapping consumed by REVA."""
        reserved = {"seeds", "conditions", "paired", "repetitions", "resource_budget"}
        conflict = reserved & set(self.evaluation_options)
        if conflict:
            raise ValueError(
                "evaluation_options cannot replace authoring controls: "
                + ", ".join(sorted(conflict))
            )
        task = copy.deepcopy(dict(self.task))
        if "task_id" in task and task["task_id"] != self.task_id:
            raise ValueError("task.task_id conflicts with PairedStudy.task_id")
        task["task_id"] = self.task_id
        experiment: dict[str, Any] = {"name": self.name}
        if self.protocol_revision is not None:
            experiment["protocol_revision"] = self.protocol_revision
        evaluation = {
            **copy.deepcopy(dict(self.evaluation_options)),
            "seeds": list(self.seeds),
            "conditions": [copy.deepcopy(dict(item)) for item in self.conditions],
            "paired": True,
            "repetitions": self.repetitions,
            "missing_outcomes": "preserve",
            "confirmation_plan": "frozen",
            "resource_budget": copy.deepcopy(dict(self.resource_budget)),
        }
        return {
            "schema": "reva.campaign.v1",
            "experiment": experiment,
            "task": task,
            "model": copy.deepcopy(dict(self.model)),
            "environments": [copy.deepcopy(dict(item)) for item in self.environments],
            "evaluation": evaluation,
            "execution": copy.deepcopy(dict(self.execution)),
            "measurement": copy.deepcopy(dict(self.measurement)),
            "outputs": copy.deepcopy(dict(self.outputs)),
        }

    def freeze(self) -> FrozenCampaignPlan:
        """Validate the authored study and return its immutable execution plan."""
        return compile_campaign_spec(self.to_spec())

    def write_spec(self, path: str | Path) -> None:
        """Validate and write the declarative source reviewed before freezing."""
        spec = self.to_spec()
        compile_campaign_spec(spec)
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(spec, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
