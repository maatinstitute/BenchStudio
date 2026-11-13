"""Executed RoboPAD source-response cache; no policy or destination authority."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceCache:
    source: str
    source_record_sha256: str
    action_bytes: bytes
    action_sha256: str
    count: int

    def prefix(self, horizon: int):
        import numpy as np

        if type(horizon) is not int or horizon not in (1, 5, 10, 20):
            raise ValueError("only prespecified assay horizons permitted")
        if horizon > self.count:
            raise ValueError("source ended before requested prefix; padding forbidden")
        return np.frombuffer(self.action_bytes, dtype="<f8").reshape(self.count, 7)[:horizon].copy()


def cache_executed_source(
    source: str, executed_actions: Any, source_record_sha256: str
) -> SourceCache:
    """Retain only the executed source prefix needed by the fixed assay."""
    import numpy as np

    if source not in ("H", "D", "I"):
        raise ValueError("explicit source-world identity required")
    if (
        not isinstance(source_record_sha256, str)
        or len(source_record_sha256) != 64
        or any(character not in "0123456789abcdef" for character in source_record_sha256)
    ):
        raise ValueError("retained source-record SHA-256 required")
    actions = np.asarray(executed_actions, dtype="<f8")
    if (
        actions.ndim != 2
        or actions.shape[1] != 7
        or len(actions) == 0
        or not np.isfinite(actions).all()
        or np.any(np.abs(actions) > 1)
    ):
        raise ValueError("finite executed normalized seven-dimensional actions required")
    data = np.ascontiguousarray(actions[:20]).tobytes()
    return SourceCache(
        source,
        source_record_sha256,
        data,
        hashlib.sha256(data).hexdigest(),
        min(len(actions), 20),
    )


def select_prefix(
    caches: dict[str, SourceCache],
    requested_source: str,
    horizon: int,
    *,
    insensitive: bool = False,
):
    """Select a matching retained source, optionally reusing held-source data."""
    source = "H" if insensitive else requested_source
    if source not in ("H", "D", "I") or source not in caches or caches[source].source != source:
        raise ValueError("matching retained source cache required")
    return caches[source].prefix(horizon)
