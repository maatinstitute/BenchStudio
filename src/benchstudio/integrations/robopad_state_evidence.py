"""Dependency-light serialization boundary for RoboPAD state evidence reports."""

from __future__ import annotations

from typing import Any


def json_numpy(value: Any) -> Any:
    """Convert NumPy scalars/arrays without stringifying unknown evidence."""
    import numpy as np

    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"Unsupported report type: {type(value).__name__}")
