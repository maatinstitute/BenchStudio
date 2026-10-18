"""π0.7-inspired episode metadata for the public π0.5 prompt path.

This module only formats already validated sidecar labels. It does not infer
quality from task success, and it does not alter the action-prediction loss.
Unknown fields are represented explicitly so missing annotations cannot become
an accidental positive label.
"""

from __future__ import annotations

import math
from typing import Any, Mapping

SCHEMA_VERSION = "outcome_metadata_v1"
_FIELDS = ("outcome", "quality", "mistake", "recovery", "speed", "provenance")
_OUTCOMES = {"success", "failure", "unknown"}
_RECOVERY = {"nominal", "recovery", "original-recovery", "corrective-recovery", "unknown"}
_MISTAKE = {"true", "false", "unknown"}
_MAX_TEXT = 256


def _text(value: Any, field: str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if field == "quality" and not 1 <= value <= 5:
            raise ValueError("quality must be in [1, 5]")
        if field == "speed" and value < 0:
            raise ValueError("speed must be nonnegative")
        return str(value)
    if isinstance(value, str) and value.strip():
        value = value.strip().lower().replace("_", "-")
        if len(value) > _MAX_TEXT:
            raise ValueError(f"{field} is too long")
        return value
    raise ValueError(f"{field} must be a nonempty string or numeric value")


def validate_metadata(metadata: Mapping[str, Any]) -> dict[str, str]:
    """Validate and normalize one metadata sidecar.

    ``quality`` and ``speed`` may be numeric or the string ``unknown``. The
    categorical labels are intentionally closed vocabularies. This function
    returns a new dictionary and never mutates a dataset record.
    """
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    extra = set(metadata) - set(_FIELDS)
    if extra:
        raise ValueError(f"unknown metadata fields: {sorted(extra)}")
    result: dict[str, str] = {}
    for field in _FIELDS:
        value = metadata.get(field, "unknown")
        if field == "outcome":
            value = _text(value, field)
            if value not in _OUTCOMES:
                raise ValueError(f"outcome must be one of {sorted(_OUTCOMES)}")
        elif field == "recovery":
            value = _text(value, field)
            if value not in _RECOVERY:
                raise ValueError(f"recovery must be one of {sorted(_RECOVERY)}")
        elif field == "mistake":
            value = _text(value, field)
            if value not in _MISTAKE:
                raise ValueError(f"mistake must be one of {sorted(_MISTAKE)}")
        elif field in {"quality", "speed"}:
            if value == "unknown":
                value = "unknown"
            else:
                if isinstance(value, bool):
                    raise ValueError(f"{field} must be numeric or unknown")
                if isinstance(value, str):
                    try:
                        numeric = float(value)
                    except ValueError as exc:
                        raise ValueError(f"{field} must be numeric or unknown") from exc
                elif isinstance(value, (int, float)):
                    numeric = float(value)
                else:
                    raise ValueError(f"{field} must be numeric or unknown")
                if not math.isfinite(numeric):
                    raise ValueError(f"{field} must be finite")
                if field == "quality" and not 1 <= numeric <= 5:
                    raise ValueError("quality must be in [1, 5]")
                value = str(value).strip()
        elif value != "unknown":
            value = _text(value, field)
        result[field] = value
    return result


def format_metadata(metadata: Mapping[str, Any]) -> str:
    """Return a deterministic, bounded prompt fragment for π0.5."""
    values = validate_metadata(metadata)
    return "Metadata: " + "; ".join(f"{field}={values[field]}" for field in _FIELDS)


def condition_prompt(task: str, metadata: Mapping[str, Any] | None = None) -> str:
    """Build the task prompt, optionally appending validated metadata.

    An absent metadata argument preserves the ordinary π0.5 prompt exactly.
    The caller is responsible for deciding whether unknown-only metadata is
    useful; the formatter keeps it explicit for auditability.
    """
    if not isinstance(task, str) or not task.strip():
        raise ValueError("task must be a nonempty string")
    prompt = task.strip()
    return prompt if metadata is None else f"{prompt}. {format_metadata(metadata)}"


def prompt_mode_metadata(
    mode: str, *, recorded_outcome: str | None = None
) -> dict[str, str] | None:
    """Return the only prompt metadata modes allowed by the campaign contract."""
    unknown = {field: "unknown" for field in _FIELDS}
    if mode == "task_only":
        if recorded_outcome is not None:
            raise ValueError("task_only cannot receive an outcome")
        return None
    if mode == "all_metadata_unknown":
        if recorded_outcome is not None:
            raise ValueError("unknown-only mode cannot receive an outcome")
        return unknown
    if mode == "recorded_outcome":
        if recorded_outcome not in {"success", "failure", "unknown"}:
            raise ValueError("recorded_outcome must be success, failure, or unknown")
        unknown["outcome"] = recorded_outcome
        return unknown
    if mode == "desired_success":
        if recorded_outcome is not None:
            raise ValueError("desired-success mode cannot receive an evaluation result")
        unknown["outcome"] = "success"
        return unknown
    raise ValueError(f"unsupported prompt mode: {mode}")
