from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..conformance.world_state import (
    ValidationIssue,
    validate_worldepisode_contract,
    validate_worldepisode_record,
)


@dataclass(frozen=True)
class WorldEpisodePreflight:
    valid: bool
    profile: str
    diagnostics: tuple[dict[str, Any], ...]


def preflight_worldepisode(
    payload: dict[str, Any],
    *,
    require_reference: bool = False,
    strict: bool = False,
    expected_episode_id: str | None = None,
    expected_revision_id: str | None = None,
) -> WorldEpisodePreflight:
    """Validate a WorldEpisode record and bind it to expected identity when supplied."""
    if not isinstance(payload, dict):
        return WorldEpisodePreflight(
            False,
            "benchstudio_invalid_worldepisode_profile",
            ({"code": "invalid_payload", "field": None, "message": "payload must be a mapping"},),
        )
    identity_diagnostics = _identity_diagnostics(
        payload,
        expected_episode_id=expected_episode_id,
        expected_revision_id=expected_revision_id,
    )
    try:
        from worldepisode.validator import validate_worldepisode
    except ImportError:
        if require_reference:
            raise RuntimeError(
                "WorldEpisode reference validator is required; install the WorldEpisode package"
            )
        diagnostics = (
            validate_worldepisode_contract(payload)
            if strict
            else validate_worldepisode_record(payload)
        )
        converted = tuple(_issue_to_dict(issue) for issue in diagnostics) + identity_diagnostics
        return WorldEpisodePreflight(
            not converted,
            "benchstudio_strict_worldepisode_profile"
            if strict
            else "benchstudio_minimal_worldepisode_profile",
            converted,
        )
    except Exception as exc:
        if require_reference:
            raise
        return WorldEpisodePreflight(
            False,
            "worldepisode_reference_validator_error",
            (
                {
                    "code": "reference_validator_error",
                    "field": None,
                    "message": f"{type(exc).__name__}: {exc}",
                },
            )
            + identity_diagnostics,
        )
    diagnostics = validate_worldepisode(payload)
    if diagnostics is None:
        diagnostics = ()
    converted = (
        tuple(_reference_issue_to_dict(diagnostic) for diagnostic in diagnostics)
        + identity_diagnostics
    )
    return WorldEpisodePreflight(not converted, "worldepisode_reference_validator", converted)


def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {"code": issue.code, "field": issue.field, "message": issue.message}


def _identity_diagnostics(
    payload: dict[str, Any],
    *,
    expected_episode_id: str | None,
    expected_revision_id: str | None,
) -> tuple[dict[str, Any], ...]:
    diagnostics: list[dict[str, Any]] = []
    episode_id = _nested_or_legacy(payload, "episode", "episode_id", "episode_id")
    revision_id = _nested_or_legacy(payload, "world_revision", "world_revision_id", "revision_id")
    if expected_episode_id is not None and episode_id != expected_episode_id:
        diagnostics.append(
            {
                "code": "episode_identity_mismatch",
                "field": "episode_id",
                "message": "episode_id does not match the frozen evaluation identity",
            }
        )
    if expected_revision_id is not None and revision_id != expected_revision_id:
        diagnostics.append(
            {
                "code": "revision_identity_mismatch",
                "field": "revision_id",
                "message": "revision_id does not match the frozen evaluation identity",
            }
        )
    return tuple(diagnostics)


def _nested_or_legacy(payload: dict[str, Any], container: str, nested: str, legacy: str) -> Any:
    value = payload.get(container)
    if isinstance(value, dict) and nested in value:
        return value.get(nested)
    return payload.get(legacy)


def _reference_issue_to_dict(issue: Any) -> dict[str, Any]:
    if hasattr(issue, "to_dict"):
        value = issue.to_dict()
        if isinstance(value, dict):
            return value
    if isinstance(issue, dict):
        return dict(issue)
    return {"code": "reference_validator_issue", "field": None, "message": str(issue)}
