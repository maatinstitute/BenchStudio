"""Deterministic archives for immutable campaign evidence bundles."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_MAX_CAMPAIGN_ARCHIVE_BYTES = 512 * 1024 * 1024


class CampaignArchiveError(ValueError):
    """Raised when a campaign bundle is invalid or unsafe to extract."""


def build_campaign_archive(root: Path, *, max_bytes: int = _MAX_CAMPAIGN_ARCHIVE_BYTES) -> bytes:
    """Freeze a completed campaign directory into reproducible ZIP bytes.

    The bundle includes the frozen plan, append-only ledger, manifests, and
    attempt artifacts present under ``root``. Scratch directories beginning
    with ``_`` and symlinks are excluded or rejected so an archive cannot
    silently bind files outside the campaign directory.
    """
    root = root.resolve()
    if not root.is_dir():
        raise CampaignArchiveError(f"campaign root is not a directory: {root}")
    files: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part.startswith("_") for part in relative.parts):
            continue
        if path.is_symlink():
            raise CampaignArchiveError(f"campaign contains symlink: {relative.as_posix()}")
        if path.is_file():
            files.append(path)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=_FIXED_ZIP_TIME)
            info.external_attr = 0o644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    payload = buffer.getvalue()
    if len(payload) > max_bytes:
        raise CampaignArchiveError(
            f"campaign archive exceeds limit ({len(payload)} > {max_bytes} bytes)"
        )
    return payload


def campaign_archive_digest(archive: bytes) -> str:
    return hashlib.sha256(archive).hexdigest()


def write_campaign_archive(root: Path, destination: Path) -> dict[str, str | int]:
    """Write a content-addressed campaign bundle without overwriting one."""
    if destination.exists():
        raise CampaignArchiveError(f"archive destination already exists: {destination}")
    archive = build_campaign_archive(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(archive)
    return {
        "path": str(destination),
        "sha256": campaign_archive_digest(archive),
        "bytes": len(archive),
    }


def extract_verified_campaign_archive(
    archive: bytes, destination: Path, *, expected_sha256: str | None = None
) -> str:
    """Verify a campaign archive and extract it without path traversal."""
    digest = campaign_archive_digest(archive)
    if expected_sha256 is not None and digest != expected_sha256:
        raise CampaignArchiveError(
            f"campaign archive digest mismatch: expected {expected_sha256}, got {digest}"
        )
    if destination.exists():
        raise CampaignArchiveError(f"destination already exists: {destination}")
    destination_root = destination.resolve()
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            members = package.infolist()
            for member in members:
                target = (destination / member.filename).resolve()
                if not target.is_relative_to(destination_root):
                    raise CampaignArchiveError(f"archive contains unsafe path: {member.filename}")
            destination.mkdir(parents=True)
            for member in members:
                package.extract(member, destination)
    except zipfile.BadZipFile as exc:
        raise CampaignArchiveError("campaign archive is not a valid ZIP") from exc
    return digest
