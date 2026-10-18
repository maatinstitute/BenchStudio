from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from .evidence import sha256_file


def generate_ed25519_keypair() -> tuple[bytes, bytes]:
    """Generate a PEM private/public key pair using the optional crypto package."""
    serialization, Ed25519PrivateKey = _crypto()
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def sign_manifest(
    manifest_path: Path,
    private_key_pem: bytes,
    signature_path: Path,
    *,
    key_id: str | None = None,
) -> dict[str, Any]:
    """Write a detached Ed25519 signature over a manifest digest."""
    serialization, _ = _crypto()
    private_key = serialization.load_pem_private_key(private_key_pem, password=None)
    manifest_sha256 = sha256_file(manifest_path)
    payload = _signature_payload(manifest_sha256)
    signature = private_key.sign(payload)
    record = {
        "schema": "benchstudio_manifest_signature_v1",
        "algorithm": "ed25519",
        "manifest_sha256": manifest_sha256,
        "signature_base64": base64.b64encode(signature).decode("ascii"),
    }
    if key_id is not None:
        if not key_id:
            raise ValueError("key_id must not be empty")
        record["key_id"] = key_id
    signature_path.parent.mkdir(parents=True, exist_ok=True)
    signature_path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    return record


def verify_manifest_signature(
    manifest_path: Path,
    signature_path: Path,
    public_key_pem: bytes,
) -> dict[str, Any]:
    """Verify a detached signature against an independently supplied public key."""
    serialization, _ = _crypto()
    try:
        record = json.loads(signature_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"valid": False, "reason": f"signature_read_error: {exc}"}
    if not isinstance(record, dict):
        return {"valid": False, "reason": "signature_not_mapping"}
    actual_digest = sha256_file(manifest_path)
    if record.get("schema") != "benchstudio_manifest_signature_v1":
        return {"valid": False, "reason": "signature_schema_mismatch"}
    if record.get("algorithm") != "ed25519":
        return {"valid": False, "reason": "signature_algorithm_mismatch"}
    signed_digest = record.get("manifest_sha256")
    if not isinstance(signed_digest, str) or not _is_hex_digest(signed_digest):
        return {"valid": False, "reason": "signed_manifest_digest_invalid"}
    if signed_digest != actual_digest:
        return {
            "valid": False,
            "reason": "signed_manifest_digest_mismatch",
            "signed_manifest_sha256": signed_digest,
            "actual_manifest_sha256": actual_digest,
        }
    signature_value = record.get("signature_base64")
    if not isinstance(signature_value, str):
        return {"valid": False, "reason": "signature_value_invalid"}
    if "key_id" in record and (not isinstance(record["key_id"], str) or not record["key_id"]):
        return {"valid": False, "reason": "key_id_invalid"}
    try:
        signature = base64.b64decode(signature_value, validate=True)
        public_key = serialization.load_pem_public_key(public_key_pem)
        public_key.verify(signature, _signature_payload(actual_digest))
    except Exception as exc:
        return {"valid": False, "reason": f"signature_verification_failed: {type(exc).__name__}"}
    result: dict[str, Any] = {
        "valid": True,
        "algorithm": record["algorithm"],
        "manifest_sha256": actual_digest,
    }
    if "key_id" in record:
        result["key_id"] = record["key_id"]
    return result


def _signature_payload(manifest_sha256: str) -> bytes:
    return json.dumps(
        {
            "schema": "benchstudio_manifest_signature_v1",
            "manifest_sha256": manifest_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _is_hex_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _crypto() -> tuple[Any, Any]:
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError(
            "manifest signing requires the optional 'cryptography' dependency"
        ) from exc
    return serialization, Ed25519PrivateKey
