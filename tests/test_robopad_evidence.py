from unittest.mock import patch

import numpy as np
import pytest

from benchstudio.integrations.robopad_evidence_codec import decode, digest, encode
from benchstudio.integrations.robopad_evidence_store import EvidenceStore


def _identity(stream="original", step=0):
    return {"cell": "parent/controller/cell/k", "stream": stream, "camera": 0, "step": step}


def _frames():
    return {
        stream + "_" + str(camera): np.full((2, 2, 3), camera, np.uint8)
        for stream in ("original", "physics")
        for camera in range(2)
    }


def test_codec_preserves_rgb_temporal_and_cross_stream_bytes():
    array = np.arange(24, dtype=np.uint8).reshape(2, 4, 3)
    metadata, payload = encode(array, _identity(), initial=True)
    np.testing.assert_array_equal(decode(metadata, payload, expected_identity=_identity()), array)
    for current, base_identity in (
        (_identity(step=1), _identity()),
        (_identity("physics", 0), _identity()),
    ):
        other = array ^ 123
        metadata, payload = encode(
            other, current, initial=False, base=array, base_identity=base_identity
        )
        np.testing.assert_array_equal(
            decode(
                metadata,
                payload,
                expected_identity=current,
                expected_base_identity=base_identity,
                base=array,
            ),
            other,
        )
        with pytest.raises(ValueError):
            decode(
                metadata, payload, expected_identity=current, expected_base_identity=base_identity
            )


def test_codec_preserves_float_nan_bits_and_rejects_corruption():
    bits = np.array(
        [0x7FC00001, 0x7FA00002, 0x80000000, 0xFF800000, 1, 0x3F800000], dtype=np.uint32
    )
    for dtype in ("<f4", ">f4"):
        array = bits.view(np.float32).reshape(1, 3, 1, 2).astype(dtype)
        metadata, payload = encode(array, _identity("query", 5), initial=True)
        assert (
            decode(metadata, payload, expected_identity=_identity("query", 5)).tobytes()
            == array.tobytes()
        )
    array = np.zeros((2, 2, 3), np.uint8)
    metadata, payload = encode(array, _identity(), initial=True)
    for bad in (payload[:-1], payload + b"junk", bytes([payload[0] ^ 1]) + payload[1:]):
        edited = {**metadata, "encoded_size": len(bad), "encoded_sha256": digest(bad)}
        with pytest.raises(ValueError):
            decode(edited, bad, expected_identity=_identity())
    with pytest.raises(ValueError):
        encode(array, _identity(step=2), initial=False, base=array, base_identity=_identity())


def test_store_commits_frames_queries_and_fails_closed(tmp_path):
    store = EvidenceStore(
        tmp_path / "cell", cell_id="trusted/cell", k=5, byte_cap=100_000, reserve=4096
    )
    store.frame(0, _frames())
    store.frame(1, _frames())
    queries = {f"query_{camera}": np.zeros((1, 3, 2, 2), np.float32) for camera in range(3)}
    store.query(5, queries)
    store.query(15, queries)
    assert len(store.commits) == 4
    with pytest.raises(ValueError):
        store.frame(1, _frames())
    assert store.failed
    with pytest.raises(RuntimeError):
        store.frame(2, _frames())


def test_store_keeps_orphans_and_rejects_tampering(tmp_path):
    store = EvidenceStore(
        tmp_path / "cell", cell_id="trusted/cell", k=5, byte_cap=100_000, reserve=4096
    )
    original = store._json

    def fail(name, value, **kwargs):
        if name.startswith("frame-000-original_0"):
            raise OSError("injected metadata write error")
        return original(name, value, **kwargs)

    with patch.object(store, "_json", side_effect=fail), pytest.raises(OSError):
        store.frame(0, _frames())
    assert (store.path / "frame-000-original_0.bin").exists()
    assert not (store.path / "frame-000.commit.json").exists()
    store2 = EvidenceStore(
        tmp_path / "cell2", cell_id="trusted/cell", k=5, byte_cap=100_000, reserve=4096
    )
    store2.frame(0, _frames())
    (store2.path / "frame-000-original_0.bin").write_bytes(b"tampered")
    with pytest.raises(ValueError):
        store2.frame(1, _frames())
    assert store2.failed
