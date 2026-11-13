from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_FIELDS = (
    "camera",
    "action_transform",
    "controller",
    "physical_parameters",
    "clock",
)


@dataclass(frozen=True)
class CalibrationRecord:
    """Pinned calibration identities used to interpret an environment run."""

    revision: str
    camera: str | None = None
    action_transform: str | None = None
    controller: str | None = None
    physical_parameters: str | None = None
    clock: str | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, field: str = "calibration"):
        if not isinstance(value, Mapping):
            raise ValueError(f"{field} must be a mapping")
        revision = value.get("revision")
        if not isinstance(revision, str) or not revision:
            raise ValueError(f"{field}.revision must be a non-empty string")
        kwargs: dict[str, str | None] = {}
        for name in _FIELDS:
            digest = value.get(name)
            if digest is not None and (
                not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None
            ):
                raise ValueError(f"{field}.{name} must be sha256:<lowercase digest>")
            kwargs[name] = digest
        return cls(revision=revision, **kwargs)

    def to_dict(self) -> dict[str, str]:
        result = {"revision": self.revision}
        result.update({name: value for name, value in self._items() if value is not None})
        return result

    def digest_sha256(self) -> str:
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _items(self):
        return ((name, getattr(self, name)) for name in _FIELDS)


@dataclass(frozen=True)
class CalibrationComparison:
    compatible: bool
    issues: tuple[str, ...]
    compared_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "compatible": self.compatible,
            "issues": list(self.issues),
            "compared_fields": list(self.compared_fields),
        }


def compare_calibrations(
    first: CalibrationRecord, second: CalibrationRecord
) -> CalibrationComparison:
    """Compare pinned calibration identities without assuming transfer equrevaence."""
    issues: list[str] = []
    compared: list[str] = []
    if first.revision != second.revision:
        issues.append("revision differs")
    for name in _FIELDS:
        left = getattr(first, name)
        right = getattr(second, name)
        if left is None or right is None:
            issues.append(f"{name} calibration is missing")
        else:
            compared.append(name)
            if left != right:
                issues.append(f"{name} calibration differs")
    return CalibrationComparison(not issues, tuple(issues), tuple(compared))


def calibration_from_environment(environment: Mapping[str, Any]) -> CalibrationRecord | None:
    value = environment.get("calibration")
    return None if value is None else CalibrationRecord.from_mapping(value)
