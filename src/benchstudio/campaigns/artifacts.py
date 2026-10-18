from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .archive import build_campaign_archive


@dataclass(frozen=True)
class ArtifactReference:
    schema: str
    digest_sha256: str
    uri: str
    bytes: int

    def to_dict(self) -> dict[str, str | int]:
        return {
            "schema": self.schema,
            "digest_sha256": self.digest_sha256,
            "uri": self.uri,
            "bytes": self.bytes,
        }


class ArtifactStore(Protocol):
    def publish_archive(self, archive: bytes, *, digest_sha256: str) -> ArtifactReference: ...


class LocalArtifactStore:
    """Idempotent content-addressed artifact store for local workers and CI."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def publish_archive(self, archive: bytes, *, digest_sha256: str) -> ArtifactReference:
        actual = hashlib.sha256(archive).hexdigest()
        if actual != digest_sha256:
            raise ValueError(f"artifact digest mismatch: expected {digest_sha256}, got {actual}")
        destination = self.root / digest_sha256[:2] / f"{digest_sha256}.zip"
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != archive:
                raise ValueError(f"artifact digest collision at {destination}")
        else:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=destination.parent, prefix=".upload-", delete=False
            ) as handle:
                temporary = Path(handle.name)
                handle.write(archive)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        return ArtifactReference(
            "benchstudio.campaign_archive.v1",
            digest_sha256,
            str(destination),
            len(archive),
        )


def publish_campaign_archive(root: Path, store: ArtifactStore) -> ArtifactReference:
    """Build and publish a deterministic campaign archive through a store."""
    archive = build_campaign_archive(root)
    digest = hashlib.sha256(archive).hexdigest()
    return store.publish_archive(archive, digest_sha256=digest)
