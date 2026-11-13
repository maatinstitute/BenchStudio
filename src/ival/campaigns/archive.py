"""Deterministic archives for immutable campaign evidence bundles."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

_FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
_MAX_CAMPAIGN_ARCHIVE_BYTES = 512 * 1024 * 1024
_LEDGER_STATUSES = {"completed", "failed", "failed_cleanup", "cancelled", "infrastructure_failure"}


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


def verify_campaign_archive(
    archive: bytes, *, expected_sha256: str | None = None
) -> dict[str, object]:
    """Verify archive integrity and structure without extracting it."""
    digest = campaign_archive_digest(archive)
    issues: list[dict[str, str]] = []
    if expected_sha256 is not None and digest != expected_sha256:
        issues.append({"reason": "trusted_digest_mismatch"})
    if len(archive) > _MAX_CAMPAIGN_ARCHIVE_BYTES:
        issues.append({"reason": "archive_too_large"})
    names: list[str] = []
    contents: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as package:
            for member in package.infolist():
                name = member.filename
                names.append(name)
                path = Path(name)
                if path.is_absolute() or ".." in path.parts:
                    issues.append({"reason": "unsafe_path", "name": name})
                if member.is_dir():
                    continue
                mode = (member.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    issues.append({"reason": "symlink_entry", "name": name})
                contents.setdefault(name, package.read(member))
            if package.testzip() is not None:
                issues.append({"reason": "corrupt_member"})
    except zipfile.BadZipFile:
        issues.append({"reason": "invalid_zip"})
    if len(names) != len(set(names)):
        issues.append({"reason": "duplicate_entry_names"})
    required = {"campaign-plan.json", "attempt-results.jsonl"}
    missing = sorted(required - set(names))
    issues.extend({"reason": "required_file_missing", "name": name} for name in missing)
    if not missing and not any(issue["reason"] == "invalid_zip" for issue in issues):
        issues.extend(_validate_campaign_contents(contents))
    return {
        "schema": "ival_campaign_archive_verification_v1",
        "digest_sha256": digest,
        "trusted_digest_supplied": expected_sha256 is not None,
        "entry_count": len(names),
        "issues": issues,
        "valid": not issues,
    }


def _validate_campaign_contents(contents: dict[str, bytes]) -> list[dict[str, str]]:
    from .frozen_plan import FrozenCampaignPlan

    issues: list[dict[str, str]] = []
    try:
        plan = FrozenCampaignPlan.from_dict(json.loads(contents["campaign-plan.json"]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return [{"reason": "invalid_campaign_plan", "detail": str(exc)}]
    planned = {attempt.key.attempt_id: attempt.key for attempt in plan.attempts}
    seen: set[str] = set()
    for index, line in enumerate(contents["attempt-results.jsonl"].splitlines()):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append({"reason": "invalid_ledger_json", "detail": f"line {index}: {exc}"})
            continue
        if not isinstance(record, dict):
            issues.append({"reason": "invalid_ledger_record", "detail": f"line {index}"})
            continue
        attempt_id = record.get("attempt_id")
        expected = planned.get(attempt_id)
        if not isinstance(attempt_id, str) or expected is None:
            issues.append({"reason": "ledger_attempt_outside_plan", "detail": str(attempt_id)})
            continue
        if attempt_id in seen:
            issues.append({"reason": "ledger_duplicate_attempt", "detail": attempt_id})
        seen.add(attempt_id)
        if record.get("plan_digest_sha256") != plan.plan_digest_sha256:
            issues.append({"reason": "ledger_plan_digest_mismatch", "detail": attempt_id})
        status = record.get("status")
        if status not in _LEDGER_STATUSES:
            issues.append({"reason": "ledger_status_invalid", "detail": f"{attempt_id}:{status}"})
        elif status == "cancelled":
            if "evidence_verified" in record and not isinstance(record["evidence_verified"], bool):
                issues.append({"reason": "ledger_evidence_flag_invalid", "detail": attempt_id})
        elif status == "infrastructure_failure":
            if record.get("evidence_verified") is not False:
                issues.append({"reason": "ledger_evidence_flag_invalid", "detail": attempt_id})
        elif record.get("evidence_verified") is not True:
            issues.append({"reason": "ledger_evidence_flag_invalid", "detail": attempt_id})
        if status in {"completed", "failed", "failed_cleanup"}:
            required_evidence = (
                f"attempts/{attempt_id}/summary.json",
                f"attempts/{attempt_id}/runtime-receipt.json",
                f"attempts/{attempt_id}/artifact-manifest.json",
                f"attempts/{attempt_id}.artifact-manifest.sha256",
            )
            for name in required_evidence:
                if name not in contents:
                    issues.append(
                        {"reason": "ledger_evidence_missing", "detail": f"{attempt_id}:{name}"}
                    )
            if all(name in contents for name in required_evidence):
                issues.extend(_validate_embedded_attempt_evidence(contents, attempt_id, status))
        for field in ("run_id", "scenario_id", "pair_id", "condition_id", "environment_id"):
            if record.get(field) != getattr(expected, field):
                issues.append(
                    {"reason": "ledger_identity_mismatch", "detail": f"{attempt_id}:{field}"}
                )
    for attempt_id in sorted(set(planned) - seen):
        issues.append({"reason": "ledger_attempt_missing", "detail": attempt_id})
    return issues


def _validate_embedded_attempt_evidence(
    contents: dict[str, bytes], attempt_id: str, ledger_status: str
) -> list[dict[str, str]]:
    """Verify one archived attempt manifest against the bytes in the bundle."""
    prefix = f"attempts/{attempt_id}/"
    manifest_name = f"{prefix}artifact-manifest.json"
    anchor_name = f"attempts/{attempt_id}.artifact-manifest.sha256"
    issues: list[dict[str, str]] = []
    run_manifest_name = f"{prefix}manifest.json"
    if run_manifest_name in contents:
        try:
            run_manifest = json.loads(contents[run_manifest_name])
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            issues.append({"reason": "run_manifest_invalid", "detail": f"{attempt_id}:{exc}"})
        else:
            issues.extend(_validate_run_manifest_dependencies(run_manifest, attempt_id))
    try:
        manifest = json.loads(contents[manifest_name])
    except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return [{"reason": "artifact_manifest_invalid", "detail": f"{attempt_id}:{exc}"}]
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema") != "ival_artifact_manifest_v1"
    ):
        issues.append({"reason": "artifact_manifest_invalid", "detail": attempt_id})
        return issues
    if manifest.get("status") != ledger_status:
        issues.append({"reason": "artifact_manifest_status_mismatch", "detail": attempt_id})
    files = manifest.get("files")
    if not isinstance(files, dict):
        return issues + [{"reason": "artifact_manifest_files_invalid", "detail": attempt_id}]
    bound_names: set[str] = set()
    for name, expected in files.items():
        if (
            not isinstance(name, str)
            or not name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
        ):
            issues.append(
                {"reason": "artifact_manifest_path_invalid", "detail": f"{attempt_id}:{name}"}
            )
            continue
        bound_names.add(name)
        if not isinstance(expected, dict):
            issues.append(
                {"reason": "artifact_manifest_entry_invalid", "detail": f"{attempt_id}:{name}"}
            )
            continue
        digest = expected.get("sha256")
        size = expected.get("bytes")
        archive_name = prefix + name
        payload = contents.get(archive_name)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            issues.append(
                {"reason": "artifact_manifest_digest_invalid", "detail": f"{attempt_id}:{name}"}
            )
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            issues.append(
                {"reason": "artifact_manifest_size_invalid", "detail": f"{attempt_id}:{name}"}
            )
        if payload is None:
            issues.append({"reason": "artifact_evidence_missing", "detail": f"{attempt_id}:{name}"})
            continue
        if isinstance(digest, str) and hashlib.sha256(payload).hexdigest() != digest:
            issues.append(
                {"reason": "artifact_evidence_digest_mismatch", "detail": f"{attempt_id}:{name}"}
            )
        if isinstance(size, int) and not isinstance(size, bool) and len(payload) != size:
            issues.append(
                {"reason": "artifact_evidence_size_mismatch", "detail": f"{attempt_id}:{name}"}
            )
    archived_names = {
        name[len(prefix) :]
        for name in contents
        if name.startswith(prefix) and name != manifest_name
    }
    for name in sorted(archived_names - bound_names):
        issues.append({"reason": "artifact_evidence_unbound", "detail": f"{attempt_id}:{name}"})
    anchor = contents.get(anchor_name)
    if anchor is not None:
        try:
            parts = anchor.decode("utf-8").strip().split()
        except UnicodeDecodeError:
            parts = []
        expected_manifest_digest = parts[-1] if len(parts) >= 3 else ""
        actual_manifest_digest = hashlib.sha256(contents[manifest_name]).hexdigest()
        if expected_manifest_digest != actual_manifest_digest:
            issues.append({"reason": "artifact_trust_anchor_mismatch", "detail": attempt_id})
    return issues


def _validate_run_manifest_dependencies(manifest: object, attempt_id: str) -> list[dict[str, str]]:
    """Validate dependency provenance embedded in a run manifest."""
    if not isinstance(manifest, dict):
        return [{"reason": "run_manifest_invalid", "detail": attempt_id}]
    issues: list[dict[str, str]] = []
    for field in ("model_dependencies", "simulator_dependencies"):
        records = manifest.get(field)
        if records is None:
            continue
        if not isinstance(records, list):
            issues.append(
                {"reason": "run_manifest_dependencies_invalid", "detail": f"{attempt_id}:{field}"}
            )
            continue
        for index, record in enumerate(records):
            valid = (
                isinstance(record, dict)
                and isinstance(record.get("name"), str)
                and bool(record["name"])
                and isinstance(record.get("import_name"), str)
                and bool(record["import_name"])
                and isinstance(record.get("available"), bool)
                and isinstance(record.get("required"), bool)
                and isinstance(record.get("scope"), str)
                and bool(record["scope"])
                and (record.get("version") is None or isinstance(record.get("version"), str))
            )
            if not valid:
                issues.append(
                    {
                        "reason": "run_manifest_dependency_invalid",
                        "detail": f"{attempt_id}:{field}:{index}",
                    }
                )
    return issues


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
