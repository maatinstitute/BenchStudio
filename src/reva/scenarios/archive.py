"""Deterministic, content-addressed scenario archives.

The archive is deliberately independent of a simulator.  A scenario directory
can contain task metadata, robot descriptions, world assets, and initial-state
files; this module freezes those bytes into a reproducible ZIP before a
campaign plan is executed.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_MAX_ARCHIVE_BYTES = 128 * 1024 * 1024


class ScenarioArchiveError(ValueError):
    """Raised when an archive is invalid or unsafe to extract."""


def build_scenario_archive(root: Path, *, max_bytes: int = _MAX_ARCHIVE_BYTES) -> bytes:
    """Build stable ZIP bytes from ``root`` and return them.

    File ordering, ZIP timestamps, permissions, and excluded scratch paths are
    fixed so identical scenario content produces identical archive bytes.
    """
    root = root.resolve()
    if not root.is_dir():
        raise ScenarioArchiveError(f"scenario root is not a directory: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        if _is_scratch(path, root):
            continue
        if path.is_symlink():
            raise ScenarioArchiveError(
                f"scenario contains symlink: {path.relative_to(root).as_posix()}"
            )
        if path.is_file():
            files.append(path)
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=_FIXED_ZIP_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    payload = buffer.getvalue()
    if len(payload) > max_bytes:
        raise ScenarioArchiveError(
            f"scenario archive exceeds limit ({len(payload)} > {max_bytes} bytes)"
        )
    return payload


def scenario_archive_digest(archive: bytes) -> str:
    """Return the SHA-256 digest used as the archive's content identity."""
    return hashlib.sha256(archive).hexdigest()


def verify_scenario_archive(
    archive: bytes, *, expected_sha256: str | None = None
) -> dict[str, object]:
    """Verify scenario archive structure and an optional independent digest."""
    digest = scenario_archive_digest(archive)
    issues: list[dict[str, str]] = []
    if expected_sha256 is not None and digest != expected_sha256:
        issues.append({"reason": "trusted_digest_mismatch"})
    if len(archive) > _MAX_ARCHIVE_BYTES:
        issues.append({"reason": "archive_too_large"})
    names: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            for member in package.infolist():
                name = member.filename
                names.append(name)
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    issues.append({"reason": "unsafe_path", "name": name})
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    issues.append({"reason": "symlink_entry", "name": name})
            if package.testzip() is not None:
                issues.append({"reason": "corrupt_member"})
    except zipfile.BadZipFile:
        issues.append({"reason": "invalid_zip"})
    if len(names) != len(set(names)):
        issues.append({"reason": "duplicate_entry_names"})
    return {
        "schema": "reva_scenario_archive_verification_v1",
        "digest_sha256": digest,
        "trusted_digest_supplied": expected_sha256 is not None,
        "entry_count": len(names),
        "issues": issues,
        "valid": not issues,
    }


def extract_verified_scenario_archive(
    archive: bytes, destination: Path, *, expected_sha256: str | None = None
) -> str:
    """Verify and safely extract an archive, returning its digest.

    Extraction rejects absolute paths and traversal entries before writing any
    member. Existing destinations are rejected to avoid merging two scenario
    identities accidentally.
    """
    if destination.exists():
        raise ScenarioArchiveError(f"destination already exists: {destination}")
    verification = verify_scenario_archive(archive, expected_sha256=expected_sha256)
    if not verification["valid"]:
        raise ScenarioArchiveError(_verification_error_message(verification["issues"]))
    digest = str(verification["digest_sha256"])
    destination_root = destination.resolve()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            members = package.infolist()
            for member in members:
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination_root):
                    raise ScenarioArchiveError(f"archive contains unsafe path: {member.filename}")
            destination.mkdir(parents=True)
            for member in members:
                package.extract(member, destination)
    except zipfile.BadZipFile as exc:
        raise ScenarioArchiveError("scenario archive is not a valid ZIP") from exc
    return digest


def _verification_error_message(issues: object) -> str:
    reasons = {
        str(issue.get("reason"))
        for issue in issues
        if isinstance(issue, dict) and issue.get("reason")
    }
    if "trusted_digest_mismatch" in reasons:
        return "scenario archive digest mismatch"
    if "invalid_zip" in reasons:
        return "scenario archive is not a valid ZIP"
    if "unsafe_path" in reasons:
        return "scenario archive contains an unsafe path"
    if "symlink_entry" in reasons:
        return "scenario archive contains a symlink"
    if "duplicate_entry_names" in reasons:
        return "scenario archive contains duplicate entries"
    if "corrupt_member" in reasons:
        return "scenario archive contains a corrupt member"
    return "scenario archive verification failed: " + ", ".join(sorted(reasons))


def _is_scratch(path: Path, root: Path) -> bool:
    return any(part.startswith("_") for part in path.relative_to(root).parts)
