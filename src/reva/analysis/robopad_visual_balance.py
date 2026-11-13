"""RoboPAD outcome-free within-parent visual matching."""

from __future__ import annotations

from typing import Any


def image_distance(before: Any, after: Any) -> float:
    """Compute signed-safe RGB MAE for uint8 or floating [0, 1] images."""
    import numpy as np

    before, after = np.asarray(before), np.asarray(after)
    if (
        before.dtype != after.dtype
        or before.shape != after.shape
        or before.ndim != 3
        or before.shape[-1] != 3
        or before.size == 0
    ):
        raise ValueError("expected equal nonempty HxWx3 images with matching dtype")
    if before.dtype == np.uint8:
        scale = 255
    elif np.issubdtype(before.dtype, np.floating):
        if any(
            not np.isfinite(value).all() or (value < 0).any() or (value > 1).any()
            for value in (before, after)
        ):
            raise ValueError("floating policy inputs must be finite and in [0,1]")
        scale = 1
    else:
        raise ValueError("expected uint8 or floating [0,1] policy inputs")
    return float(np.abs(before.astype(np.float64) - after.astype(np.float64)).mean() / scale)


def _check(rows: list[dict[str, Any]]) -> None:
    import numpy as np

    seen: set[str] = set()
    for row in rows:
        if set(row) != {"id", "distance", "physical_valid"}:
            raise ValueError("candidate accepts only identity, distances and physical validity")
        name = row["id"]
        if not isinstance(name, str) or not name or name in seen:
            raise ValueError("candidate identity must be unique and nonempty")
        seen.add(name)
        if type(row["physical_valid"]) is not bool:
            raise ValueError("physical validity must be explicitly true or false")
        values = np.asarray(row["distance"], dtype=float)
        if (
            values.shape != (2,)
            or not np.isfinite(values).all()
            or (values < 0).any()
            or (values > 1).any()
        ):
            raise ValueError("two finite per-camera distances in [0,1] required")


def match_candidates(
    relevant: list[dict[str, Any]], irrelevant: list[dict[str, Any]]
) -> dict[str, Any]:
    """Select one deterministic balanced pair and retain every rejection."""
    import numpy as np

    relevant, irrelevant = list(relevant), list(irrelevant)
    _check(relevant)
    _check(irrelevant)
    choices: list[tuple[float, str, str, list[float], list[float]]] = []
    for relevant_row in relevant:
        for irrelevant_row in irrelevant:
            if not relevant_row["physical_valid"] or not irrelevant_row["physical_valid"]:
                continue
            relevant_distance = np.asarray(relevant_row["distance"], dtype=float)
            irrelevant_distance = np.asarray(irrelevant_row["distance"], dtype=float)
            if (relevant_distance == 0).any() or (irrelevant_distance == 0).any():
                continue
            delta = np.abs(relevant_distance - irrelevant_distance)
            ratio = relevant_distance / irrelevant_distance
            if (delta <= 0.01).all() and (ratio >= 0.8).all() and (ratio <= 1.25).all():
                choices.append(
                    (
                        float(delta.max()),
                        relevant_row["id"],
                        irrelevant_row["id"],
                        delta.tolist(),
                        ratio.tolist(),
                    )
                )
    choice = min(choices) if choices else None
    selected = (
        None
        if choice is None
        else {
            "relevant": choice[1],
            "irrelevant": choice[2],
            "per_camera_absolute_difference": choice[3],
            "per_camera_ratio": choice[4],
        }
    )
    return {
        "match": selected,
        "reason": "matched" if selected else "no_balanced_pair",
        "unmatched_relevant": sorted(
            row["id"]
            for row in relevant
            if row["physical_valid"] and (not choice or row["id"] != choice[1])
        ),
        "unmatched_irrelevant": sorted(
            row["id"]
            for row in irrelevant
            if row["physical_valid"] and (not choice or row["id"] != choice[2])
        ),
        "invalid_relevant": sorted(row["id"] for row in relevant if not row["physical_valid"]),
        "invalid_irrelevant": sorted(row["id"] for row in irrelevant if not row["physical_valid"]),
    }
