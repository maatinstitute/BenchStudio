from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..conformance.world_state import ValidationIssue, validate_worldepisode_contract


@dataclass(frozen=True)
class WorldEpisodePreflight:
    valid: bool
    profile: str
    diagnostics: tuple[dict[str, Any], ...]


PROFILE = "benchstudio_worldepisode_contract_v1"


def preflight_worldepisode(
    payload: dict[str, Any],
    *,
    expected_episode_id: str | None = None,
    expected_revision_id: str | None = None,
) -> WorldEpisodePreflight:
    """Validate the single canonical contract and bind its nested identity.

    This validator is local and deterministic. It never changes behavior based
    on optional packages installed in the current Python environment.
    """
    if not isinstance(payload, dict):
        return WorldEpisodePreflight(
            False,
            PROFILE,
            ({"code": "invalid_payload", "field": None, "message": "payload must be a mapping"},),
        )
    diagnostics = [_issue_to_dict(issue) for issue in validate_worldepisode_contract(payload)]
    episode = payload.get("episode")
    revision = payload.get("world_revision")
    episode_id = episode.get("episode_id") if isinstance(episode, dict) else None
    revision_id = revision.get("world_revision_id") if isinstance(revision, dict) else None
    if expected_episode_id is not None and episode_id != expected_episode_id:
        diagnostics.append(
            {
                "code": "episode_identity_mismatch",
                "field": "episode.episode_id",
                "message": "episode.episode_id does not match the frozen evaluation identity",
            }
        )
    if expected_revision_id is not None and revision_id != expected_revision_id:
        diagnostics.append(
            {
                "code": "revision_identity_mismatch",
                "field": "world_revision.world_revision_id",
                "message": "world_revision.world_revision_id does not match the frozen evaluation identity",
            }
        )
    return WorldEpisodePreflight(not diagnostics, PROFILE, tuple(diagnostics))


def _issue_to_dict(issue: ValidationIssue) -> dict[str, Any]:
    return {"code": issue.code, "field": issue.field, "message": issue.message}
