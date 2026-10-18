"""Portable scenario identity and content-addressed task-pack metadata."""

from .archive import (
    ScenarioArchiveError,
    build_scenario_archive,
    extract_verified_scenario_archive,
    scenario_archive_digest,
)
from .packs import ScenarioPack, load_scenario_pack, validate_scenario_pack

__all__ = [
    "ScenarioPack",
    "load_scenario_pack",
    "validate_scenario_pack",
    "ScenarioArchiveError",
    "build_scenario_archive",
    "extract_verified_scenario_archive",
    "scenario_archive_digest",
]
