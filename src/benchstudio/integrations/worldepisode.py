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
    payload: dict[str, Any], *, require_reference: bool = False, strict: bool = False
) -> WorldEpisodePreflight:
    """Use the canonical validator when installed, with an explicit minimal fallback."""
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
        return WorldEpisodePreflight(
            not diagnostics,
            "benchstudio_strict_worldepisode_profile"
            if strict
            else "benchstudio_minimal_worldepisode_profile",
            tuple(_issue_to_dict(issue) for issue in diagnostics),
        )
    diagnostics = validate_worldepisode(payload)
    converted = tuple(
        diagnostic.to_dict() if hasattr(diagnostic, "to_dict") else dict(diagnostic)
        for diagnostic in diagnostics
    )
    return WorldEpisodePreflight(not diagnostics, "worldepisode_reference_validator", converted)


def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {"code": issue.code, "field": issue.field, "message": issue.message}
