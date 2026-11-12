"""Opt-in, same-host mmap tensor transport for persistent policy processes.

Large numeric arrays move through private temporary files rather than JSON
lists. On Linux the default uses /dev/shm (tmpfs); elsewhere it may be backed
by disk. This is a transport boundary, not GPU sharing or VLA preprocessing.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import uuid
from collections.abc import Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = "benchstudio.local_array.v1"
_MARKER = "__benchstudio_local_array__"
_FILENAME = re.compile(r"[0-9a-f]{32}\.bin\Z")
_MAX_ELEMENTS = 128 * 1024 * 1024


def _numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("local tensor transport requires numpy in both processes") from exc
    return np


def _valid_dtype(dtype: Any) -> bool:
    return dtype.kind in "biuf" and dtype.itemsize in (1, 2, 4, 8)


class MappedTensorPublisher:
    """Own per-request files and unlink them even on inference errors/timeouts."""

    def __init__(self, *, directory: str | None = None, max_bytes: int = 256 * 1024 * 1024):
        if type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("max_bytes must be a positive integer")
        if directory is None and os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
            directory = "/dev/shm"
        self._temp = tempfile.TemporaryDirectory(prefix="benchstudio-arrays-", dir=directory)
        self.root = Path(self._temp.name)
        self.max_bytes = max_bytes
        self._closed = False

    @contextmanager
    def publish(self, value: Any) -> Iterator[Any]:
        if self._closed:
            raise RuntimeError("local tensor publisher is closed")
        np = _numpy()
        paths: list[Path] = []
        used_bytes = 0
        array_count = 0

        def encode(item: Any) -> Any:
            nonlocal used_bytes, array_count
            if isinstance(item, np.ndarray):
                if not _valid_dtype(item.dtype) or item.size == 0:
                    raise ValueError("local transport requires nonempty numeric or boolean arrays")
                if used_bytes + item.nbytes > self.max_bytes or array_count >= 64:
                    raise ValueError("local tensor transport size/count limit exceeded")
                array = np.ascontiguousarray(item)
                filename = uuid.uuid4().hex + ".bin"
                path = self.root / filename
                view = memoryview(array).cast("B")
                digest = hashlib.sha256(view).hexdigest()
                with path.open("xb") as stream:
                    os.chmod(path, 0o600)
                    stream.write(view)
                paths.append(path)
                used_bytes += array.nbytes
                array_count += 1
                return {_MARKER: {
                    "schema": SCHEMA,
                    "filename": filename,
                    "shape": list(array.shape),
                    "dtype": array.dtype.str,
                    "nbytes": array.nbytes,
                    "sha256": digest,
                }}
            if isinstance(item, np.generic):
                return item.item()
            if isinstance(item, Mapping):
                if not all(isinstance(k, str) for k in item):
                    raise ValueError("local tensor transport requires string mapping keys")
                return {key: encode(child) for key, child in item.items()}
            if isinstance(item, (list, tuple)):
                return [encode(child) for child in item]
            if item is None or isinstance(item, (str, int, float, bool)):
                return item
            raise TypeError(f"unsupported local transport value: {type(item).__name__}")

        try:
            yield encode(value)
        finally:
            for path in paths:
                path.unlink(missing_ok=True)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._temp.cleanup()


def _checked_array_info(spec: Any, root: Path) -> tuple[Path, Any, tuple[int, ...], int, str]:
    np = _numpy()
    if not isinstance(spec, dict) or set(spec) != {
        "schema", "filename", "shape", "dtype", "nbytes", "sha256"
    } or spec.get("schema") != SCHEMA:
        raise ValueError("invalid local tensor descriptor schema")
    name = spec["filename"]
    if not isinstance(name, str) or not _FILENAME.fullmatch(name):
        raise ValueError("invalid local tensor filename")
    shape = spec["shape"]
    if (
        not isinstance(shape, list)
        or not shape
        or any(type(dim) is not int or dim < 1 for dim in shape)
    ):
        raise ValueError("invalid local tensor shape")
    count = 1
    for dim in shape:
        count *= dim
        if count > _MAX_ELEMENTS:
            raise ValueError("local tensor shape exceeds limit")
    dtype_name = spec["dtype"]
    if not isinstance(dtype_name, str) or len(dtype_name) > 16:
        raise ValueError("invalid local tensor dtype")
    try:
        dtype = np.dtype(dtype_name)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid local tensor dtype") from exc
    if not _valid_dtype(dtype):
        raise ValueError("unsupported local tensor dtype")
    nbytes = spec["nbytes"]
    if type(nbytes) is not int or nbytes != count * dtype.itemsize:
        raise ValueError("local tensor byte count does not match shape and dtype")
    digest = spec["sha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("invalid local tensor digest")
    path = root / name
    if not path.is_file() or path.is_symlink() or path.stat().st_size != nbytes:
        raise ValueError("local tensor file missing or has invalid size")
    return path, dtype, tuple(shape), nbytes, digest


@contextmanager
def open_local_tensors(value: Any, *, root: str) -> Iterator[Any]:
    """Resolve descriptors only inside the publisher's private same-host directory.

    Callers must finish model inference before leaving this context. mmap-backed
    arrays are copy-on-write to avoid mutating the publisher's original inputs.
    """
    if not root:
        raise ValueError("local tensor root must be configured explicitly")
    np = _numpy()
    directory = Path(root).resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("local tensor root is not a directory")
    arrays: list[Any] = []

    def decode(item: Any) -> Any:
        if isinstance(item, dict) and _MARKER in item:
            if set(item) != {_MARKER}:
                raise ValueError("local tensor descriptor has unexpected fields")
            path, dtype, shape, nbytes, digest = _checked_array_info(item[_MARKER], directory)
            mapped = np.memmap(path, dtype=dtype, mode="c", shape=shape)
            if hashlib.sha256(memoryview(mapped).cast("B")).hexdigest() != digest:
                mapped._mmap.close()
                raise ValueError("local tensor payload digest mismatch")
            arrays.append(mapped)
            return mapped
        if isinstance(item, dict):
            return {key: decode(child) for key, child in item.items()}
        if isinstance(item, list):
            return [decode(child) for child in item]
        return item

    try:
        yield decode(value)
    finally:
        # The inference caller must have released any torch views first.
        for mapped in arrays:
            mapped._mmap.close()
