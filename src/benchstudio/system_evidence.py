"""Validated, simulator-independent evidence bundles for composed system runs.

The source of task success is a declared evaluator. This module never
invents a success criterion, downloads weights or executes a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
import hashlib
from functools import lru_cache
import json
import math
from pathlib import Path
import re
from typing import Any, Mapping

from .system_spec import SystemSpec


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty")
    return value


@lru_cache(maxsize=256)
def _validated_sha(value: str) -> str:
    if re.fullmatch("[0-9a-f]{64}", value) is None:
        raise ValueError("expected lowercase SHA-256")
    return value


def _sha(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("expected lowercase SHA-256")
    if type(value) is str:
        return _validated_sha(value)
    # Preserve subclass behavior without invoking custom hashing or __str__.
    return _validated_sha.__wrapped__(value)


@dataclass(frozen=True)
class TrialKey:
    task: str
    task_revision: str
    scenario: str
    condition: str
    seed: int
    repetition: int
    environment_revision: str
    protocol_digest: str
    evaluator: str
    evaluator_revision: str

    def __post_init__(self) -> None:
        for name in ("task", "task_revision", "scenario", "condition",
                     "environment_revision", "evaluator", "evaluator_revision"):
            _required(getattr(self, name), name)
        if type(self.seed) is not int or type(self.repetition) is not int or self.repetition < 0:
            raise ValueError("seed and nonnegative repetition must be integers")
        _sha(self.protocol_digest)


_KEY_FIELDS = tuple(f.name for f in fields(TrialKey))


@dataclass(frozen=True)
class Trial:
    trial_id: str
    key: TrialKey
    system_digest: str
    status: str
    success: bool | None
    outcome_source: str
    authoritative: bool
    metrics: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required(self.trial_id, "trial_id")
        _sha(self.system_digest)
        if self.status not in {"completed", "execution_failed", "missing", "cancelled"}:
            raise ValueError("invalid execution status")
        if self.outcome_source not in {"official", "declared", "supplementary"}:
            raise ValueError("invalid outcome source")
        if type(self.authoritative) is not bool:
            raise ValueError("authoritative must be boolean")
        if self.outcome_source == "supplementary" and self.authoritative:
            raise ValueError("supplementary outcome cannot claim authority")
        if self.success is not None and type(self.success) is not bool:
            raise ValueError("success must be true, false or null")
        if self.status != "completed" and self.success is not None:
            raise ValueError("incomplete execution cannot have success result")
        if not isinstance(self.metrics, Mapping):
            raise ValueError("metrics must be a mapping")
        for name, value in self.metrics.items():
            if not isinstance(name, str) or not name or type(value) not in (int, float):
                raise ValueError("metric must have string name and numeric value")
            if not math.isfinite(value):
                raise ValueError("metrics must be finite")

    @property
    def valid_success(self) -> bool:
        return self.status == "completed" and self.authoritative and self.success is not None

    def to_dict(self) -> dict[str, Any]:
        # The schema contains validated scalars plus two mappings. Copy those
        # mappings explicitly instead of recursively deep-copying every scalar.
        return {
            "trial_id": self.trial_id,
            "key": {name: getattr(self.key, name) for name in _KEY_FIELDS},
            "system_digest": self.system_digest,
            "status": self.status,
            "success": self.success,
            "outcome_source": self.outcome_source,
            "authoritative": self.authoritative,
            "metrics": dict(self.metrics),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Trial":
        if not isinstance(value, Mapping) or set(value) - {
            "trial_id", "key", "system_digest", "status", "success",
            "outcome_source", "authoritative", "metrics"
        }:
            raise ValueError("invalid trial record")
        return cls(
            trial_id=value["trial_id"], key=TrialKey(**value["key"]),
            system_digest=value["system_digest"], status=value["status"],
            success=value["success"], outcome_source=value["outcome_source"],
            authoritative=value["authoritative"], metrics=value.get("metrics", {}),
        )


@dataclass(frozen=True)
class SystemRun:
    run_id: str
    system: SystemSpec
    trials: tuple[Trial, ...]
    source_digests: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _required(self.run_id, "run_id")
        if len({t.trial_id for t in self.trials}) != len(self.trials):
            raise ValueError("duplicate trial_id")
        if len({t.key for t in self.trials}) != len(self.trials):
            raise ValueError("duplicate experimental identity")
        if any(t.system_digest != self.system.digest for t in self.trials):
            raise ValueError("trial is bound to a different system")


    def summary(self) -> str:
        completed = sum(t.status == "completed" for t in self.trials)
        valid = sum(t.valid_success for t in self.trials)
        return f"{self.run_id}: {completed}/{len(self.trials)} completed; {valid} authoritative binary outcomes"

    def save(self, root: str | Path) -> Path:
        """Retain the existing system-run evidence format; never overwrite a directory."""
        root = Path(root)
        root.mkdir(parents=True, exist_ok=False)
        return _write_run(self, root)


def _write_run(run: SystemRun, root: Path) -> Path:
    with (root / "system.json").open("x", encoding="utf-8") as stream:
        json.dump(run.system.to_dict(), stream, sort_keys=True)
    with (root / "trials.jsonl").open("x", encoding="utf-8") as stream:
        for trial in run.trials:
            stream.write(json.dumps(trial.to_dict(), sort_keys=True) + "\n")
    manifest = {"schema": "benchstudio.system_run.v1", "run_id": run.run_id,
                "files": {name: _digest_file(root / name) for name in ("system.json", "trials.jsonl")}}
    # Manifest is last: a partial write is not readable as a completed run.
    with (root / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, sort_keys=True)
    return root


def _file(root: Path, name: str) -> Path:
    if root.is_symlink():
        raise ValueError("symlinked evidence root")
    path = root / name
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"missing or symlinked evidence file: {name}")
    return path


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_run(root: str | Path) -> SystemRun:
    """Read trusted-format evidence without rerunning or re-scoring the system."""
    root = Path(root)
    manifest = json.loads(_file(root, "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "benchstudio.system_run.v1" or set(manifest) != {
        "schema", "run_id", "files"
    }:
        raise ValueError("unsupported or malformed system run manifest")
    if not isinstance(manifest["files"], dict) or set(manifest["files"]) != {
        "system.json", "trials.jsonl"
    }:
        raise ValueError("manifest must bind system.json and trials.jsonl")
    for name, expected in manifest["files"].items():
        if _digest_file(_file(root, name)) != _sha(expected):
            raise ValueError(f"evidence digest mismatch: {name}")
    system = SystemSpec.from_dict(json.loads(_file(root, "system.json").read_text("utf-8")))
    trials = []
    with _file(root, "trials.jsonl").open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    trials.append(Trial.from_dict(json.loads(line)))
                except (ValueError, KeyError, TypeError) as exc:
                    raise ValueError(f"invalid trial line {line_number}: {exc}") from exc
    return SystemRun(
        run_id=manifest["run_id"], system=system,
        trials=tuple(trials), source_digests=dict(manifest["files"]),
    )

