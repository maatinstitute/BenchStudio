"""Optional numpy tests; core IVal imports without numpy."""
import json

import pytest

np = pytest.importorskip("numpy")
from ival.local_tensors import MappedTensorPublisher, open_local_tensors  # noqa: E402


def test_roundtrip_preserves_shape_dtype_and_bytes():
    image = np.arange(3 * 4 * 3, dtype=np.uint8).reshape(3, 4, 3)
    publisher = MappedTensorPublisher(max_bytes=1024)
    try:
        with publisher.publish({"policy_batch": {"front": image, "state": [1, 2]}}) as payload:
            json.dumps(payload)
            info = payload["policy_batch"]["front"]["__ival_local_array__"]
            assert len(json.dumps(payload)) < 600
            assert (publisher.root / info["filename"]).exists()
            with open_local_tensors(payload, root=str(publisher.root)) as output:
                np.testing.assert_array_equal(output["policy_batch"]["front"], image)
                assert output["policy_batch"]["front"].dtype == image.dtype
                assert output["policy_batch"]["state"] == [1, 2]
        assert not (publisher.root / info["filename"]).exists()
    finally:
        publisher.close()
    assert not publisher.root.exists()


def test_local_tensor_publisher_cleans_after_exception():
    publisher = MappedTensorPublisher()
    with pytest.raises(RuntimeError, match="stopped"):
        with publisher.publish({"frame": np.ones((8, 8), dtype=np.uint8)}):
            raise RuntimeError("stopped")
    assert list(publisher.root.iterdir()) == []
    publisher.close()


def test_local_tensor_publisher_rejects_object_and_overbudget():
    publisher = MappedTensorPublisher(max_bytes=32)
    try:
        with pytest.raises(ValueError, match="nonempty numeric"):
            with publisher.publish({"bad": np.array(["oops"])}):
                pass
        with pytest.raises(ValueError, match="size/count limit"):
            with publisher.publish({"bad": np.ones((8, 8), dtype=np.uint8)}):
                pass
        assert list(publisher.root.iterdir()) == []
    finally:
        publisher.close()


def test_local_tensor_rejects_tampering_and_path_escape():
    publisher = MappedTensorPublisher()
    try:
        with publisher.publish(np.arange(5, dtype=np.float32)) as descriptor:
            name = descriptor["__ival_local_array__"]["filename"]
            path = publisher.root / name
            with path.open("r+b") as f:
                f.write(b"bogus")
            with pytest.raises(ValueError, match="digest mismatch"):
                with open_local_tensors(descriptor, root=str(publisher.root)):
                    pass
            descriptor["__ival_local_array__"]["filename"] = "../../secret.bin"
            with pytest.raises(ValueError, match="filename"):
                with open_local_tensors(descriptor, root=str(publisher.root)):
                    pass
    finally:
        publisher.close()


def test_local_tensor_rejects_missing_root_and_closed_publisher():
    publisher = MappedTensorPublisher()
    publisher.close()
    with pytest.raises(RuntimeError, match="closed"):
        with publisher.publish(np.array([1])):
            pass
    with pytest.raises(ValueError, match="root"):
        with open_local_tensors({}, root=""):
            pass
