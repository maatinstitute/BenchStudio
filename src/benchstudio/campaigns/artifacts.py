from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.error
import urllib.request
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


class HttpArtifactStore:
    """Vendor-neutral HTTP PUT store for digest-addressed campaign archives."""

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        timeout_s: float = 30.0,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self.base_url = base_url.rstrip("/")
        self.headers = dict(headers or {})
        self.timeout_s = timeout_s

    def publish_archive(self, archive: bytes, *, digest_sha256: str) -> ArtifactReference:
        actual = hashlib.sha256(archive).hexdigest()
        if actual != digest_sha256:
            raise ValueError(f"artifact digest mismatch: expected {digest_sha256}, got {actual}")
        uri = f"{self.base_url}/{digest_sha256[:2]}/{digest_sha256}.zip"
        request = urllib.request.Request(
            uri,
            data=archive,
            method="PUT",
            headers={
                **self.headers,
                "Content-Type": "application/zip",
                "Content-Length": str(len(archive)),
                "If-None-Match": "*",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if not 200 <= response.status < 300:
                    raise OSError(f"artifact upload failed with HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            if exc.code not in {409, 412}:
                raise OSError(f"artifact upload failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"artifact upload failed: {exc.reason}") from exc
        return ArtifactReference(
            "benchstudio.campaign_archive.v1",
            digest_sha256,
            uri,
            len(archive),
        )


def publish_campaign_archive(root: Path, store: ArtifactStore) -> ArtifactReference:
    """Build and publish a deterministic campaign archive through a store."""
    archive = build_campaign_archive(root)
    digest = hashlib.sha256(archive).hexdigest()
    return store.publish_archive(archive, digest_sha256=digest)
