from __future__ import annotations

import hashlib
import urllib.error

import pytest

from benchstudio.campaigns import (
    CampaignExecutor,
    CampaignPlanner,
    HttpArtifactStore,
    LocalArtifactStore,
    publish_campaign_archive,
    retrieve_campaign_archive,
)


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


def test_local_artifact_store_retrieves_and_verifies_campaign_archive(tmp_path):
    from benchstudio.mock import MockPolicy, MockSimulator

    plan = CampaignPlanner(
        run_id="retrieve", scenario_id="task", conditions=[{"x": 1}], seeds=[1]
    ).freeze()
    campaign = tmp_path / "campaign"
    CampaignExecutor(plan, campaign, lambda _: MockPolicy(), lambda _: MockSimulator()).run()
    store = LocalArtifactStore(tmp_path / "store")
    reference = publish_campaign_archive(campaign, store)
    extracted = tmp_path / "extracted"
    assert (
        retrieve_campaign_archive(store, reference.digest_sha256, extracted)
        == reference.digest_sha256
    )
    assert (extracted / "campaign-plan.json").is_file()


def test_publish_campaign_archive_returns_verified_reference(tmp_path):
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "campaign-plan.json").write_text("{}\n", encoding="utf-8")
    reference = publish_campaign_archive(campaign, LocalArtifactStore(tmp_path / "store"))
    assert reference.schema == "benchstudio.campaign_archive.v1"
    assert len(reference.digest_sha256) == 64
    assert reference.bytes > 0


def test_http_artifact_store_publishes_digest_addressed_archive(monkeypatch):
    calls = []

    class Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 2:
            raise urllib.error.HTTPError(request.full_url, 412, "exists", {}, None)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    payload = b"campaign-archive"
    digest = hashlib.sha256(payload).hexdigest()
    store = HttpArtifactStore("https://objects.example.test")
    first = store.publish_archive(payload, digest_sha256=digest)
    second = store.publish_archive(payload, digest_sha256=digest)
    assert first.uri == second.uri == f"https://objects.example.test/{digest[:2]}/{digest}.zip"
    assert calls[0][0].data == payload
    assert calls[0][0].get_header("If-none-match") == "*"


def test_http_artifact_store_retrieves_and_verifies_digest(monkeypatch):
    payload = b"campaign-archive"
    digest = hashlib.sha256(payload).hexdigest()

    class Response:
        status = 200

        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda _request, timeout: Response())
    archive = HttpArtifactStore("https://objects.example.test").fetch_archive(digest_sha256=digest)
    assert archive == payload
