"""Source-backed AlpaBridge policy-registry core.

This ports the reusable registry machinery from AlpaBridge's
``driver/policy_registry.py``. Product-specific model factories are injected by
the owning runtime; IVal keeps the registry, precondition, and
configuration semantics dependency-free.
"""

from __future__ import annotations

import importlib
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Callable, Protocol

LOGGER = logging.getLogger("ival.alpabridge_policy_registry")


class PolicyContext(Protocol):
    checkpoint_path: Any
    tokenizer_checkpoint_path: Any


PolicyFactory = Callable[[PolicyContext], Any]


@dataclass(frozen=True)
class DriverPolicy:
    name: str
    factory: PolicyFactory
    requires_checkpoint: bool = False
    requires_tokenizer_checkpoint: bool = False


class PolicyRegistry:
    """Duplicate-safe source registry with explicit construction preconditions."""

    def __init__(self) -> None:
        self._policies: dict[str, DriverPolicy] = {}

    def register(self, policy: DriverPolicy) -> None:
        if policy.name in self._policies:
            raise ValueError(f"policy {policy.name!r} is already registered")
        self._policies[policy.name] = policy

    def available(self) -> tuple[str, ...]:
        return tuple(sorted(self._policies))

    def build(self, name: str, context: PolicyContext) -> Any:
        policy = self._policies.get(name)
        if policy is None:
            raise ValueError(f"Unsupported policy: {name}")
        if policy.requires_checkpoint and context.checkpoint_path is None:
            raise ValueError(f"{name} requires a checkpoint path")
        if policy.requires_tokenizer_checkpoint and context.tokenizer_checkpoint_path is None:
            raise ValueError(f"{name} requires a tokenizer checkpoint path")
        return policy.factory(context)


def load_external_policy_modules(spec: str | None = None) -> tuple[str, ...]:
    raw = os.environ.get("ALPABRIDGE_EXTRA_POLICY_MODULES") if spec is None else spec
    if not raw or not raw.strip():
        return ()
    loaded: list[str] = []
    for name in (part.strip() for part in raw.split(",")):
        if not name:
            continue
        importlib.import_module(name)
        LOGGER.info("imported external policy module %s", name)
        loaded.append(name)
    return tuple(loaded)


def read_positive_finite_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        LOGGER.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    if not math.isfinite(value) or value <= 0:
        LOGGER.warning("%s=%s must be a positive finite number; using %s", name, value, default)
        return default
    return value


def read_finite_float_tuple(name: str, default: tuple[float, ...]) -> tuple[float, ...]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        values = tuple(float(part) for part in raw.split(",") if part.strip())
    except ValueError:
        LOGGER.warning("%s=%r is not a comma-separated float list; using %s", name, raw, default)
        return default
    if not values or not all(math.isfinite(value) for value in values):
        LOGGER.warning("%s=%r is unusable; using %s", name, raw, default)
        return default
    return values
