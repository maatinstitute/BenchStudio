"""RoboPAD's versioned bounded bit-exact evidence chunks."""

from __future__ import annotations

import hashlib
import math
import zlib
from typing import Any

MAX_BYTES = 2_000_000
FIELDS = {
    "version",
    "identity",
    "shape",
    "dtype",
    "initial",
    "base_identity",
    "base_sha256",
    "decoded_sha256",
    "encoded_sha256",
    "encoded_size",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def identity(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"cell", "stream", "camera", "step"}:
        raise ValueError("identity schema")
    if not isinstance(value["cell"], str) or not value["cell"] or len(value["cell"]) > 256:
        raise ValueError("cell identity")
    if value["stream"] not in ("original", "physics", "query"):
        raise ValueError("stream")
    if type(value["camera"]) is not int or not 0 <= value["camera"] <= 2:
        raise ValueError("camera")
    if type(value["step"]) is not int or not 0 <= value["step"] <= 200:
        raise ValueError("step")
    return dict(value)


def layout(shape: Any, dtype: str, stream: str) -> tuple[int, int]:
    if not isinstance(shape, (tuple, list)) or any(
        type(value) is not int or value <= 0 for value in shape
    ):
        raise ValueError("dimensions")
    if stream == "query":
        if len(shape) != 4 or tuple(shape[:2]) != (1, 3) or dtype not in ("<f4", ">f4"):
            raise ValueError("query shape/dtype")
        width = 4
    else:
        if len(shape) != 3 or shape[-1] != 3 or dtype != "|u1":
            raise ValueError("RGB shape/dtype")
        width = 1
    size = math.prod(shape) * width
    if size > MAX_BYTES:
        raise ValueError("decoded allocation ceiling")
    return size, width


def relationship(current: dict[str, Any], base: Any, initial: bool) -> None:
    if type(initial) is not bool:
        raise ValueError("explicit initial flag required")
    if initial:
        if (
            base is not None
            or current["stream"] == "physics"
            or (current["stream"] == "original" and current["step"] != 0)
        ):
            raise ValueError("invalid initial chunk")
        return
    if base is None:
        raise ValueError("missing base identity")
    base = identity(base)
    if base["cell"] != current["cell"] or base["camera"] != current["camera"]:
        raise ValueError("cross-cell/camera base")
    if current["stream"] == "physics":
        if base["stream"] != "original" or base["step"] != current["step"]:
            raise ValueError("physics requires corresponding original")
    elif base["stream"] != current["stream"] or base["step"] != current["step"] - (
        10 if current["stream"] == "query" else 1
    ):
        raise ValueError("reordered/skipped predecessor")


def encode(
    array: Any,
    chunk_identity: dict[str, Any],
    *,
    initial: bool,
    base: Any = None,
    base_identity: Any = None,
):
    import numpy as np

    current = identity(chunk_identity)
    array = np.asarray(array)
    shape = list(array.shape)
    dtype = array.dtype.str
    _, width = layout(shape, dtype, current["stream"])
    relationship(current, base_identity, initial)
    raw = np.ascontiguousarray(array).tobytes()
    base_raw = None
    if not initial:
        if (
            base is None
            or np.asarray(base).shape != array.shape
            or np.asarray(base).dtype.str != dtype
        ):
            raise ValueError("missing/mismatched base array")
        base_raw = np.ascontiguousarray(base).tobytes()
    elif base is not None:
        raise ValueError("unexpected initial base")
    value = np.frombuffer(raw, dtype=np.uint8)
    if base_raw is not None:
        value = np.bitwise_xor(value, np.frombuffer(base_raw, dtype=np.uint8))
    transformed = value.reshape(-1, width).T.tobytes() if width == 4 else value.tobytes()
    payload = zlib.compress(transformed, 6)
    metadata = dict(
        version=1,
        identity=current,
        shape=shape,
        dtype=dtype,
        initial=initial,
        base_identity=None if initial else identity(base_identity),
        base_sha256=None if initial else digest(base_raw),
        decoded_sha256=digest(raw),
        encoded_sha256=digest(payload),
        encoded_size=len(payload),
    )
    return metadata, payload


def decode(
    metadata: dict[str, Any],
    payload: bytes,
    *,
    expected_identity: dict[str, Any],
    expected_base_identity: dict[str, Any] | None = None,
    base: Any = None,
):
    import numpy as np

    if (
        not isinstance(metadata, dict)
        or set(metadata) != FIELDS
        or type(metadata.get("version")) is not int
        or metadata["version"] != 1
    ):
        raise ValueError("unsupported metadata/version")
    current = identity(metadata["identity"])
    if current != identity(expected_identity):
        raise ValueError("chunk identity mismatch")
    size, width = layout(metadata["shape"], metadata["dtype"], current["stream"])
    relationship(current, metadata["base_identity"], metadata["initial"])
    if metadata["base_identity"] != expected_base_identity:
        raise ValueError("base identity mismatch")
    if (
        not isinstance(payload, bytes)
        or type(metadata["encoded_size"]) is not int
        or len(payload) != metadata["encoded_size"]
        or len(payload) > MAX_BYTES + 10_000
    ):
        raise ValueError("encoded bounds")
    if digest(payload) != metadata["encoded_sha256"]:
        raise ValueError("encoded checksum")
    if metadata["initial"]:
        if base is not None or metadata["base_sha256"] is not None:
            raise ValueError("unexpected base")
        base_raw = None
    else:
        if (
            base is None
            or list(np.asarray(base).shape) != metadata["shape"]
            or np.asarray(base).dtype.str != metadata["dtype"]
        ):
            raise ValueError("base array schema")
        base_raw = np.ascontiguousarray(base).tobytes()
        if digest(base_raw) != metadata["base_sha256"]:
            raise ValueError("wrong base bytes")
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(payload, size + 1)
    except zlib.error as exc:
        raise ValueError("invalid compressed data") from exc
    if len(raw) != size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise ValueError("truncated/trailing/excess decoded data")
    value = np.frombuffer(raw, dtype=np.uint8)
    if width == 4:
        value = value.reshape(width, -1).T.reshape(-1)
    if base_raw is not None:
        value = np.bitwise_xor(value, np.frombuffer(base_raw, dtype=np.uint8))
    decoded = value.tobytes()
    if digest(decoded) != metadata["decoded_sha256"]:
        raise ValueError("decoded checksum")
    return (
        np.frombuffer(decoded, dtype=np.dtype(metadata["dtype"])).reshape(metadata["shape"]).copy()
    )
