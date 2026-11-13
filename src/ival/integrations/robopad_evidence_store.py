"""RoboPAD's single-writer, fail-closed per-cell evidence store."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from .robopad_evidence_codec import MAX_BYTES, decode, encode

META_CAP = 1_000_000


class EvidenceStore:
    """Write bounded frame/query chunks and expose commits only after verification."""

    def __init__(self, path: Path, *, cell_id: str, k: int, byte_cap: int, reserve: int = 100_000):
        import numpy as np  # noqa: F401 - fail early when the optional store is used

        if not isinstance(cell_id, str) or not cell_id or len(cell_id) > 256:
            raise ValueError("cell identity")
        if type(k) is not int or k not in (1, 5, 10, 20):
            raise ValueError("horizon")
        if type(byte_cap) is not int or type(reserve) is not int or not 4096 <= reserve < byte_cap:
            raise ValueError("quota/reserve")
        self.path = Path(path)
        self.path.mkdir(exist_ok=False)
        self.cell_id = cell_id
        self.k = k
        self.cap = byte_cap
        self.reserve = reserve
        self.failed = False
        self.frame_next = 0
        self.query_next = k
        self.previous: dict[str, tuple[Any, dict[str, Any]]] = {}
        self.previous_files: dict[str, dict[str, str]] = {}
        self.commits: list[str] = []
        try:
            self._json(
                "store.json",
                {"version": 1, "cell": cell_id, "k": k, "byte_cap": byte_cap, "reserve": reserve},
            )
        except Exception as exc:
            self._fail(exc)
            raise

    def used_bytes(self) -> int:
        total = 0
        for path in self.path.iterdir():
            if path.is_symlink() or not path.is_file():
                raise ValueError("unexpected store entry")
            total += path.stat().st_size
        return total

    def _write(self, name: str, blob: bytes, *, final: bool = False) -> None:
        limit = self.cap if final else self.cap - self.reserve
        if self.used_bytes() + len(blob) > limit:
            raise ValueError("evidence byte ceiling")
        with (self.path / name).open("xb") as stream:
            if stream.write(blob) != len(blob):
                raise OSError("short write")

    def _json(self, name: str, value: dict[str, Any], *, final: bool = False) -> None:
        blob = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if len(blob) > META_CAP:
            raise ValueError("metadata ceiling")
        self._write(name, blob, final=final)

    def _fail(self, exc: Exception) -> None:
        self.failed = True
        try:
            self._json(
                "failure.json",
                {
                    "status": "failed_closed",
                    "error": str(exc)[:1000],
                    "frames_committed": self.frame_next,
                    "queries_committed": (self.query_next - self.k) // 10,
                    "retained_bytes": self.used_bytes(),
                },
                final=True,
            )
        except Exception:
            pass

    def _identity(self, stream: str, camera: int, step: int) -> dict[str, Any]:
        return {"cell": self.cell_id, "stream": stream, "camera": camera, "step": step}

    def _chunk(self, label: str, array: Any, chunk_identity: dict[str, Any], base: Any):
        metadata, payload = encode(
            array,
            chunk_identity,
            initial=base is None,
            base=None if base is None else base[0],
            base_identity=None if base is None else base[1],
        )
        reconstructed = decode(
            metadata,
            payload,
            expected_identity=chunk_identity,
            expected_base_identity=None if base is None else base[1],
            base=None if base is None else base[0],
        )
        if (
            reconstructed.dtype != array.dtype
            or reconstructed.shape != array.shape
            or reconstructed.tobytes() != array.tobytes()
        ):
            raise ValueError("roundtrip mismatch")
        self._write(label + ".bin", payload)
        self._json(label + ".json", metadata)
        payload_path = self.path / (label + ".bin")
        metadata_path = self.path / (label + ".json")
        expected_metadata = json.dumps(
            metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if (
            payload_path.stat().st_size != len(payload)
            or payload_path.read_bytes() != payload
            or metadata_path.read_bytes() != expected_metadata
        ):
            raise ValueError("persisted content mismatch")
        return {
            "payload": label + ".bin",
            "metadata": label + ".json",
            "decoded_sha256": metadata["decoded_sha256"],
            "payload_sha256": metadata["encoded_sha256"],
            "metadata_sha256": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        }

    def _commit(self, label: str, record: dict[str, Any]) -> None:
        temporary = label + ".commit.tmp"
        target = self.path / (label + ".commit.json")
        self._json(temporary, record)
        if self.used_bytes() + (self.path / temporary).stat().st_size > self.cap - self.reserve:
            raise ValueError("commit link exceeds quota")
        os.link(self.path / temporary, target)
        if self.used_bytes() > self.cap - self.reserve:
            raise ValueError("commit link exceeds quota")

    def _unit(self, kind: str, step: int, arrays: dict[str, Any]) -> None:
        import numpy as np

        if self.failed:
            raise RuntimeError("store already failed; no retries")
        try:
            expected = self.frame_next if kind == "frame" else self.query_next
            if type(step) is not int or step != expected or not 0 <= step <= 200:
                raise ValueError("sequence mismatch")
            keys = (
                {"original_0", "original_1", "physics_0", "physics_1"}
                if kind == "frame"
                else {"query_0", "query_1", "query_2"}
            )
            if not isinstance(arrays, dict) or set(arrays) != keys:
                raise ValueError("camera/stream coverage")
            for key, array in arrays.items():
                if not isinstance(array, np.ndarray) or array.nbytes > MAX_BYTES:
                    raise ValueError("array type/allocation bound")
                if kind == "frame" and (
                    array.dtype != np.uint8 or array.ndim != 3 or array.shape[-1] != 3
                ):
                    raise ValueError("RGB schema")
                if kind == "query" and (
                    array.dtype.str not in ("<f4", ">f4")
                    or array.ndim != 4
                    or tuple(array.shape[:2]) != (1, 3)
                ):
                    raise ValueError("query schema")
            label = f"{kind}-{step:03d}"
            chunks: list[dict[str, Any]] = []
            updates: dict[str, tuple[Any, dict[str, Any]]] = {}
            file_updates: dict[str, dict[str, str]] = {}
            for key in keys:
                if key in self.previous_files:
                    saved = self.previous_files[key]
                    for field, bound in (("payload", MAX_BYTES + 10_000), ("metadata", META_CAP)):
                        path = self.path / saved[field]
                        if (
                            path.stat().st_size > bound
                            or hashlib.sha256(path.read_bytes()).hexdigest()
                            != saved[field + "_sha256"]
                        ):
                            raise ValueError("predecessor file tampered")
            for key in sorted(keys):
                stream, camera_text = key.rsplit("_", 1)
                camera = int(camera_text)
                current = self._identity(stream, camera, step)
                base = (
                    (arrays[f"original_{camera}"], self._identity("original", camera, step))
                    if stream == "physics"
                    else self.previous.get(key)
                )
                chunks.append(self._chunk(label + "-" + key, arrays[key], current, base))
                if stream != "physics":
                    updates[key] = (arrays[key].copy(), current)
                    file_updates[key] = chunks[-1]
            self._commit(
                label,
                {"version": 1, "cell": self.cell_id, "kind": kind, "step": step, "chunks": chunks},
            )
            self.previous.update(updates)
            self.previous_files.update(file_updates)
            self.commits.append(label)
            if kind == "frame":
                self.frame_next += 1
            else:
                self.query_next += 10
        except Exception as exc:
            self._fail(exc)
            raise

    def frame(self, step: int, arrays: dict[str, Any]) -> None:
        self._unit("frame", step, arrays)

    def query(self, step: int, arrays: dict[str, Any]) -> None:
        self._unit("query", step, arrays)
