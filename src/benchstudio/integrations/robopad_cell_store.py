"""RoboPAD per-cell semantic evidence and partial-rollout journal."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

from .robopad_evidence_store import EvidenceStore


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CellStore(EvidenceStore):
    """Extend the bounded chunk store with semantic and terminal evidence."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.semantic = hashlib.sha256()
        self.finished = False

    def _semantic(self, label: str, arrays: dict[str, Any]) -> None:
        import numpy as np

        self.semantic.update(label.encode())
        for key, array in sorted(arrays.items()):
            self.semantic.update(
                json.dumps(
                    [key, array.dtype.str, list(array.shape)], separators=(",", ":")
                ).encode()
            )
            self.semantic.update(np.ascontiguousarray(array).tobytes())

    def frame(self, step: int, arrays: dict[str, Any]) -> None:
        if self.finished:
            raise RuntimeError("finished store")
        super().frame(step, arrays)
        self._semantic("frame" + str(step), arrays)

    def query(self, step: int, arrays: dict[str, Any]) -> None:
        if self.finished:
            raise RuntimeError("finished store")
        super().query(step, arrays)
        self._semantic("query" + str(step), arrays)

    def aux(self, index: int, arrays: dict[str, Any], metadata: dict[str, Any]) -> None:
        import numpy as np

        if self.failed or self.finished:
            raise RuntimeError("closed evidence store")
        try:
            if type(index) is not int or not 0 <= index <= 1000:
                raise ValueError("aux index")
            if not isinstance(arrays, dict) or not arrays or len(arrays) > 200:
                raise ValueError("aux array schema")
            total = 0
            for key, array in arrays.items():
                if (
                    not isinstance(key, str)
                    or len(key) > 100
                    or not isinstance(array, np.ndarray)
                    or array.dtype.kind not in "biuf"
                    or array.nbytes > 2_000_000
                ):
                    raise ValueError("numeric aux bounds")
                total += array.nbytes
            if total > 8_000_000:
                raise ValueError("aux allocation cap")
            memory = io.BytesIO()
            np.savez_compressed(memory, **arrays)
            blob = memory.getvalue()
            if len(blob) > 9_000_000:
                raise ValueError("encoded aux cap")
            name = f"aux-{index:04d}"
            self._write(name + ".npz", blob)
            path = self.path / (name + ".npz")
            if path.stat().st_size != len(blob) or _sha(path) != hashlib.sha256(blob).hexdigest():
                raise ValueError("aux persisted bytes mismatch")
            with np.load(path, allow_pickle=False) as retained:
                if set(retained.files) != set(arrays) or any(
                    retained[key].dtype != array.dtype
                    or retained[key].shape != array.shape
                    or retained[key].tobytes() != array.tobytes()
                    for key, array in arrays.items()
                ):
                    raise ValueError("aux roundtrip mismatch")
            self._commit(
                name,
                {
                    "arrays": name + ".npz",
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "metadata": metadata,
                },
            )
            self._semantic(name, arrays)
            self.semantic.update(
                json.dumps(
                    metadata, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            )
        except Exception as exc:
            self._fail(exc)
            raise

    def partial_result(self, result: dict[str, Any]) -> dict[str, Any]:
        """Persist bounded actions even when ordinary evidence failed."""
        import numpy as np

        if self.finished:
            raise RuntimeError("terminal receipt already published")
        arrays = {key: np.asarray(result[key]) for key in ("actions", "reward", "done")}
        count = len(arrays["actions"])
        if (
            not 0 <= count <= 200
            or arrays["actions"].shape != (count, 7)
            or arrays["reward"].shape != (count,)
            or arrays["done"].shape != (count,)
        ):
            raise ValueError("partial journal shape/count")
        if any(
            array.dtype.kind not in "biuf" or not np.isfinite(array).all()
            for array in arrays.values()
        ):
            raise ValueError("partial journal invalid numeric values")
        pending = result.get("pending_action")
        if pending is not None:
            pending = np.asarray(pending)
            if pending.shape != (7,) or not np.isfinite(pending).all():
                raise ValueError("pending command shape")
            arrays["pending_action_execution_unknown"] = pending.copy()
        memory = io.BytesIO()
        np.savez_compressed(memory, **arrays)
        blob = memory.getvalue()
        if len(blob) > 24_000:
            raise ValueError("partial journal encoded cap")
        self._write("partial-actions.npz", blob, final=True)
        if _sha(self.path / "partial-actions.npz") != hashlib.sha256(blob).hexdigest():
            raise ValueError("partial journal persisted hash")
        metadata = {
            "status": "partial_actions_retained_not_complete_rollout",
            "actions": count,
            "arrays_sha256": hashlib.sha256(blob).hexdigest(),
            "failure_stage": str(result.get("failure_stage", "wall_clock_stop"))[:100],
            "termination": str(result.get("termination", "unknown"))[:100],
            "pending_execution_unknown": pending is not None,
        }
        temporary = "partial-actions.commit.tmp"
        self._json(temporary, metadata, final=True)
        if self.used_bytes() + (self.path / temporary).stat().st_size > self.cap:
            raise ValueError("partial commit reserved quota")
        import os

        os.link(self.path / temporary, self.path / "partial-actions.commit.json")
        return metadata

    def finish(self, record: dict[str, Any]) -> dict[str, Any]:
        if self.finished:
            raise RuntimeError("duplicate terminal receipt")
        self.finished = True
        receipt = dict(
            record,
            store_failed=self.failed,
            frames_retained=self.frame_next,
            queries_retained=(self.query_next - self.k) // 10,
            semantic_sha256=self.semantic.hexdigest(),
            retained_bytes_before_receipt=self.used_bytes(),
        )
        self._json("terminal.json", receipt, final=True)
        return receipt
