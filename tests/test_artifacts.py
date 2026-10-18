from __future__ import annotations

import hashlib

import pytest

from benchstudio.campaigns import LocalArtifactStore, publish_campaign_archive


def test_local_artifact_store_is_content_addressed_and_idempotent(tmp_path):
    store = LocalArtifactStore(tmp_path / "store")
    payload = b"immutable-campaign"
    digest = hashlib.sha256(payload).hexdigest()
    first = store.publish_archive(payload, digest_sha256=digest)
    second = store.publish_archive(payload, digest_sha256=digest)
    assert first == second
    assert first.digest_sha256 == digest
    assert first.bytes == len(payload)
    assert (tmp_path / "store" / digest[:2] / f"{digest}.zip").read_bytes() == payload


def test_local_artifact_store_rejects_bad_digest(tmp_path):
    store = LocalArtifactStore(tmp_path / "store")
    with pytest.raises(ValueError, match="digest mismatch"):
        store.publish_archive(b"payload", digest_sha256="0" * 64)


def test_publish_campaign_archive_returns_verified_reference(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "campaign-plan.json").write_text("{}\n", encoding="utf-8")
    reference = publish_campaign_archive(campaign, LocalArtifactStore(tmp_path / "store"))
    assert reference.schema == "benchstudio.campaign_archive.v1"
    assert len(reference.digest_sha256) == 64
    assert reference.bytes > 0
