from __future__ import annotations

import json

from benchstudio.evidence import (
    build_artifact_manifest,
    verify_artifact_manifest,
    write_manifest_trust_anchor,
)
from benchstudio.evidence_signing import (
    generate_ed25519_keypair,
    sign_manifest,
    verify_manifest_signature,
)


def test_detached_manifest_signature_is_independently_verifiable(tmp_path):
    root = tmp_path / "attempt"
    root.mkdir()
    (root / "summary.json").write_text('{"status":"completed"}\n', encoding="utf-8")
    manifest_path = root / "artifact-manifest.json"
    manifest_path.write_text(
        __import__("json").dumps(build_artifact_manifest(root, status="completed")) + "\n",
        encoding="utf-8",
    )
    private_key, public_key = generate_ed25519_keypair()
    signature_path = tmp_path / "attempt.artifact-manifest.sig"
    signed = sign_manifest(manifest_path, private_key, signature_path, key_id="worker-a")
    write_manifest_trust_anchor(manifest_path, tmp_path / "attempt.artifact-manifest.sha256")
    assert signed["key_id"] == "worker-a"
    assert verify_manifest_signature(manifest_path, signature_path, public_key)["valid"] is True
    result = verify_artifact_manifest(
        root,
        signature_path=signature_path,
        trusted_public_key=public_key,
    )
    assert result["valid"] is True
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8"
    )
    assert verify_manifest_signature(manifest_path, signature_path, public_key)["valid"] is False


def test_signature_requires_external_public_key(tmp_path):
    root = tmp_path / "attempt"
    root.mkdir()
    (root / "summary.json").write_text("{}\n", encoding="utf-8")
    manifest_path = root / "artifact-manifest.json"
    manifest_path.write_text(
        __import__("json").dumps(build_artifact_manifest(root, status="completed")) + "\n",
        encoding="utf-8",
    )
    private_key, _ = generate_ed25519_keypair()
    signature_path = tmp_path / "attempt.artifact-manifest.sig"
    sign_manifest(manifest_path, private_key, signature_path)
    result = verify_artifact_manifest(root, signature_path=signature_path)
    assert result["valid"] is False
    assert "public_key_missing" in {item["reason"] for item in result["mismatches"]}


def test_manifest_signature_verifier_rejects_malformed_signature_records(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    signature_path = tmp_path / "manifest.sig"
    signature_path.write_text("[]", encoding="utf-8")
    _, public_key = generate_ed25519_keypair()
    result = verify_manifest_signature(manifest_path, signature_path, public_key)
    assert result == {"valid": False, "reason": "signature_not_mapping"}


def test_manifest_signature_verifier_rejects_invalid_digest_and_key_id(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")
    signature_path = tmp_path / "manifest.sig"
    signature_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio_manifest_signature_v1",
                "algorithm": "ed25519",
                "manifest_sha256": "not-a-digest",
                "signature_base64": "AA==",
                "key_id": 3,
            }
        ),
        encoding="utf-8",
    )
    _, public_key = generate_ed25519_keypair()
    result = verify_manifest_signature(manifest_path, signature_path, public_key)
    assert result == {"valid": False, "reason": "signed_manifest_digest_invalid"}
