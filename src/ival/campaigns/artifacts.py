from __future__ import annotations

import hashlib
import os
import re
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .archive import (
    CampaignArchiveError,
    build_campaign_archive,
    extract_verified_campaign_archive,
    verify_campaign_archive,
)


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


class ArtifactReader(Protocol):
    def fetch_archive(self, *, digest_sha256: str) -> bytes: ...


class LocalArtifactStore:
    """Idempotent content-addressed artifact store for local workers and CI."""

    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def publish_archive(self, archive: bytes, *, digest_sha256: str) -> ArtifactReference:
        _validate_digest(digest_sha256)
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
            "ival.campaign_archive.v1",
            digest_sha256,
            str(destination),
            len(archive),
        )

    def fetch_archive(self, *, digest_sha256: str) -> bytes:
        _validate_digest(digest_sha256)
        path = self.root / digest_sha256[:2] / f"{digest_sha256}.zip"
        try:
            archive = path.read_bytes()
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"artifact not found: {digest_sha256}") from exc
        _verify_fetched_archive(archive, digest_sha256)
        return archive


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
        _validate_digest(digest_sha256)
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
            "ival.campaign_archive.v1",
            digest_sha256,
            uri,
            len(archive),
        )

    def fetch_archive(self, *, digest_sha256: str) -> bytes:
        _validate_digest(digest_sha256)
        uri = f"{self.base_url}/{digest_sha256[:2]}/{digest_sha256}.zip"
        request = urllib.request.Request(uri, method="GET", headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                if not 200 <= response.status < 300:
                    raise OSError(f"artifact download failed with HTTP {response.status}")
                archive = response.read()
        except urllib.error.HTTPError as exc:
            raise OSError(f"artifact download failed with HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"artifact download failed: {exc.reason}") from exc
        _verify_fetched_archive(archive, digest_sha256)
        return archive


def publish_campaign_archive(root: Path, store: ArtifactStore) -> ArtifactReference:
    """Build and publish a deterministic campaign archive through a store."""
    archive = build_campaign_archive(root)
    digest = hashlib.sha256(archive).hexdigest()
    return store.publish_archive(archive, digest_sha256=digest)


def retrieve_campaign_archive(store: ArtifactReader, digest_sha256: str, destination: Path) -> str:
    """Fetch, verify, and safely extract a content-addressed campaign archive."""
    archive = store.fetch_archive(digest_sha256=digest_sha256)
    verification = verify_campaign_archive(archive, expected_sha256=digest_sha256)
    if not verification["valid"]:
        raise CampaignArchiveError(f"invalid fetched campaign archive: {verification['issues']}")
    return extract_verified_campaign_archive(archive, destination, expected_sha256=digest_sha256)


def _verify_fetched_archive(archive: bytes, digest_sha256: str) -> None:
    _validate_digest(digest_sha256)
    actual = hashlib.sha256(archive).hexdigest()
    if actual != digest_sha256:
        raise ValueError(
            f"downloaded artifact digest mismatch: expected {digest_sha256}, got {actual}"
        )


def _validate_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("artifact digest must be a lowercase SHA-256 hex digest")
