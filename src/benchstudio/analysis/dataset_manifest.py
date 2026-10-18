"""Fail-closed resolver for the SmolVLA outcome-conditioning sidecar."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

WINDOW = 50
OUTCOMES = {"success", "failure", "unknown"}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(row: dict[str, Any], key: str) -> Any:
    if key not in row:
        raise ValueError(f"missing dataset field: {key}")
    return row[key]


def _path(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise ValueError(f"{field} must be a relative path")
    result = (root / value).resolve()
    if root not in result.parents:
        raise ValueError(f"{field} escapes manifest directory")
    if not result.is_file():
        raise ValueError(f"missing {field}: {value}")
    return result


def _check_hash(root: Path, row: dict[str, Any], path_field: str, hash_field: str) -> Path:
    path = _path(root, _require(row, path_field), path_field)
    expected = _require(row, hash_field)
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{hash_field} must be a SHA256 hex digest")
    if _digest(path) != expected:
        label = path_field.removesuffix("_path")
        raise ValueError(f"{label} hash mismatch")
    return path


def _validate_row(root: Path, row: dict[str, Any], purpose: str) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise ValueError("dataset rows must be objects")
    for field in (
        "sample_id",
        "episode_id",
        "task",
        "parent_id",
        "branch",
        "trajectory_id",
        "split",
    ):
        if not isinstance(_require(row, field), str) or not row[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if type(_require(row, "task_id")) is not int:
        raise ValueError("task_id must be an integer")
    observation = _check_hash(root, row, "observation_path", "observation_sha256")
    evidence = _check_hash(root, row, "outcome_evidence_path", "outcome_evidence_sha256")
    actions = _check_hash(root, row, "action_path", "action_sha256")
    outcome = _require(row, "outcome")
    if outcome not in OUTCOMES:
        raise ValueError(f"invalid outcome: {outcome}")
    if outcome == "unknown":
        if purpose == "training":
            raise ValueError("unknown outcome cannot enter training")
        return {
            "sample_id": row["sample_id"],
            "outcome": outcome,
            "exclusion_reason": "unknown_outcome",
        }
    if purpose == "training" and row["split"] != "train":
        raise ValueError("training sample has foreign split")
    if row.get("action_trajectory_id") != row["trajectory_id"]:
        raise ValueError("observation and action trajectory mismatch")
    if row.get("action_finite") is not True:
        raise ValueError("action_finite must be true")
    shape = row.get("action_shape")
    if not (
        isinstance(shape, list)
        and len(shape) == 2
        and type(shape[0]) is int
        and type(shape[1]) is int
        and shape[1] == 7
    ):
        raise ValueError("action_shape must be [T, 7]")
    start = row.get("action_start")
    frame = row.get("observation_frame_index")
    if type(start) is not int or start < 0 or type(frame) is not int or frame != start:
        raise ValueError("observation must be the pre-action frame")
    if start + WINDOW > shape[0]:
        raise ValueError("target window must contain 50 actions")
    boundaries = row.get("handoff_boundaries", [])
    if not isinstance(boundaries, list) or any(
        type(boundary) is not int for boundary in boundaries
    ):
        raise ValueError("handoff_boundaries must be integer indices")
    if any(start < boundary < start + WINDOW for boundary in boundaries):
        raise ValueError("target window crosses a handoff boundary")
    # Reading the evidence file is intentionally not interpreted here; its bytes
    # are bound above and native predicate semantics remain a separate audit.
    del observation, evidence, actions
    normalized = dict(row)
    normalized["valid_positions"] = WINDOW
    normalized["observation_path"] = str((root / row["observation_path"]).resolve())
    normalized["action_path"] = str((root / row["action_path"]).resolve())
    normalized["outcome_evidence_path"] = str((root / row["outcome_evidence_path"]).resolve())
    return normalized


@dataclass(frozen=True)
class DatasetResolution:
    rows: tuple[dict[str, Any], ...]
    exclusions: tuple[dict[str, Any], ...]
    manifest_sha256: str

    def summary(self) -> dict[str, Any]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "accepted_rows": len(self.rows),
            "excluded_rows": len(self.exclusions),
            "outcomes": {
                outcome: sum(row.get("outcome") == outcome for row in self.rows)
                for outcome in sorted(OUTCOMES - {"unknown"})
            },
            "exclusions": list(self.exclusions),
        }


def resolve_manifest(path: str | Path, *, purpose: str = "training") -> DatasetResolution:
    """Validate a sidecar without loading array payloads or altering source files."""
    if purpose not in {"training", "inventory"}:
        raise ValueError("purpose must be training or inventory")
    manifest_path = Path(path).resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != "outcome_dataset_v1":
        raise ValueError("unsupported dataset schema")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("dataset rows must be a nonempty list")
    accepted: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        sample_id = row.get("sample_id") if isinstance(row, dict) else None
        if sample_id in seen:
            raise ValueError(f"duplicate sample_id: {sample_id}")
        seen.add(sample_id)
        normalized = _validate_row(manifest_path.parent, row, purpose)
        if "exclusion_reason" in normalized:
            exclusions.append({"sample_id": sample_id, "reason": normalized["exclusion_reason"]})
        else:
            accepted.append(normalized)
    return DatasetResolution(tuple(accepted), tuple(exclusions), _digest(manifest_path))
