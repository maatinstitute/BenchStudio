"""Public pipeline for replaying existing RoboPAD validation evidence."""

from __future__ import annotations

import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

from .replay_manifest import ReplayEnvironmentError, ReplayManifest
from .replay_worker import ReplayLimits, ReplayWorkerError, execute_in_worker
from .robopad import RoboPADReplay

_MAX_ARCHIVE_BYTES = 16 * 1024**3
_MAX_ARCHIVE_MEMBERS = 100_000


def _extract(source: Path, destination: Path) -> Path:
    seen: set[PurePosixPath] = set()
    size = 0
    with tarfile.open(source, mode="r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if (
                name.is_absolute() or ".." in name.parts or "\\" in member.name
                or (not member.isdir() and not member.isfile())
            ):
                raise ValueError(f"unsafe archive entry: {member.name}")
            if name == PurePosixPath(".") and member.isdir():
                continue
            if name in seen:
                raise ValueError(f"duplicate archive entry: {member.name}")
            seen.add(name)
            if member.size < 0:
                raise ValueError(f"invalid archive entry size: {member.name}")
            size += member.size
            if len(seen) > _MAX_ARCHIVE_MEMBERS or size > _MAX_ARCHIVE_BYTES:
                raise ValueError("archive exceeds the replay extraction limits")
            target = destination.joinpath(*name.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                stream = archive.extractfile(member)
                if stream is None:
                    raise ValueError(f"cannot read archive entry: {member.name}")
                with stream, target.open("xb") as output:
                    shutil.copyfileobj(stream, output)
    if (destination / "manifest.json").is_file():
        return destination
    folders = list(destination.iterdir())
    if len(folders) == 1 and (folders[0] / "manifest.json").is_file():
        return folders[0]
    raise ValueError("archive must contain one RoboPAD campaign manifest at its root")


@dataclass(frozen=True)
class ReplayResult:
    """Detailed replay evidence with a compact user-facing summary."""

    report: dict[str, Any]
    environment: dict[str, Any] | None = None

    def summary(self) -> dict[str, Any]:
        return {
            "episode": self.report["episode"],
            "passed": self.report["passed"],
            "first_difference": self.report["first_difference"],
            "difference_count": len(self.report["differences"]),
            "environment_checked": self.environment is not None,
        }


@dataclass(frozen=True)
class ReplayPipeline:
    """Replay a saved RoboPAD nominal validation attempt from its archive."""

    archive: Path
    episode: str | None = None
    trusted_manifest_sha256: str | None = None
    limits: ReplayLimits | None = None

    @classmethod
    def from_archive(
        cls, path: str | Path, *, episode: str | None = None,
        trusted_manifest_sha256: str | None = None,
        limits: ReplayLimits | None = None,
    ) -> ReplayPipeline:
        source = Path(path).resolve()
        if not source.is_dir() and not source.is_file():
            raise FileNotFoundError(f"replay archive not found: {source}")
        if limits is not None and not isinstance(limits, ReplayLimits):
            raise TypeError("limits must be a ReplayLimits instance")
        return cls(source, episode, trusted_manifest_sha256, limits)

    def __call__(self) -> ReplayResult:
        return self.run()

    def check(self) -> dict[str, Any]:
        """Verify archive inputs and render the selected reset state."""
        return self._execute(check_only=True, verify_environment=True)

    def run(self, *, verify_environment: bool = True) -> ReplayResult:
        """Replay against the original archive, optionally probing readiness first."""
        if self.trusted_manifest_sha256 is not None and verify_environment is not True:
            raise ValueError("trusted replay requires verify_environment=True")
        return self._execute(check_only=False, verify_environment=verify_environment)

    def _execute(self, *, check_only: bool, verify_environment: bool) -> Any:
        if self.limits is not None:
            return self._execute_worker(check_only, verify_environment)
        if self.archive.is_dir():
            if self.trusted_manifest_sha256 is not None:
                raise ValueError("trusted replay requires a .tar.gz so evidence is privately staged")
            return self._run_folder(self.archive, check_only, verify_environment)
        try:
            with TemporaryDirectory(prefix="benchstudio-replay-") as temporary:
                root = _extract(self.archive, Path(temporary))
                return self._run_folder(root, check_only, verify_environment)
        except tarfile.TarError as exc:
            raise ValueError("expected a RoboPAD .tar.gz archive or extracted campaign directory") from exc

    def _execute_worker(self, check_only: bool, verify_environment: bool) -> Any:
        payload = execute_in_worker({
            "archive": str(self.archive),
            "episode": self.episode,
            "trusted_manifest_sha256": self.trusted_manifest_sha256,
            "check_only": check_only,
            "verify_environment": verify_environment,
        }, self.limits)
        status = payload["status"]
        if status == "environment_error":
            raise ReplayEnvironmentError(payload["report"])
        if status == "invalid_input":
            raise ValueError(payload["message"])
        if status == "worker_error":
            raise ReplayWorkerError(payload["message"])
        result = payload["result"]
        return result if check_only else ReplayResult(result["report"], result["environment"])

    def _run_folder(
        self, root: Path, check_only: bool, verify_environment: bool
    ) -> ReplayResult | dict[str, Any]:
        manifest = ReplayManifest.open(
            root, self.episode, trusted_sha256=self.trusted_manifest_sha256
        )
        attempt = RoboPADReplay.open(root, episode=manifest.episode)
        environment = manifest.check(attempt) if verify_environment else None
        if environment is not None:
            environment["input_trust"] = (
                "independent_manifest_digest" if self.trusted_manifest_sha256 is not None
                else "archive_declared"
            )
        if check_only:
            return environment
        if environment is not None and not environment["ready"]:
            raise ReplayEnvironmentError(environment)
        return ReplayResult(attempt.replay(), environment)

