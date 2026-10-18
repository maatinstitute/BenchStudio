"""RoboPAD outcome-free intervention proposals and static support screening."""

from __future__ import annotations

from typing import Any

FOOTPRINT_MARGIN_M = 0.01
MAX_SUPPORT_PENETRATION_M = 0.001


def irrelevant_candidates(
    anchor: Any,
    *,
    nq: int,
    nv: int,
    target_qpos: int,
    distractor_qpos: int,
    distractor_dof: int,
) -> list[dict[str, Any]]:
    """Generate the fixed 4-radius × 8-angle distractor grid."""
    import numpy as np

    fields = (nq, nv, target_qpos, distractor_qpos, distractor_dof)
    if any(type(value) is not int for value in fields):
        raise ValueError("integer model addresses required")
    if nq <= 0 or nv <= 0 or min(target_qpos, distractor_qpos, distractor_dof) < 0:
        raise ValueError("invalid model dimensions or joint addresses")
    if max(target_qpos, distractor_qpos) + 7 > nq or distractor_dof + 6 > nv:
        raise ValueError("free joint exceeds state dimensions")
    if abs(target_qpos - distractor_qpos) < 7:
        raise ValueError("target and distractor joints overlap")
    anchor_array = np.asarray(anchor, dtype=np.float64)
    if anchor_array.shape != (1 + nq + nv,) or not np.isfinite(anchor_array).all():
        raise ValueError("finite flattened simulator state required")
    q = 1 + distractor_qpos
    velocity = 1 + nq + distractor_dof
    center = anchor_array[1 + target_qpos : 3 + target_qpos]
    rows: list[dict[str, Any]] = []
    for millimeters in (40, 70, 100, 130):
        for degrees in range(0, 360, 45):
            angle = np.deg2rad(degrees)
            state = anchor_array.copy()
            state[q : q + 2] = center + (millimeters / 1000) * np.array(
                [np.cos(angle), np.sin(angle)]
            )
            state[velocity : velocity + 6] = 0
            rows.append(
                {
                    "id": f"I_r{millimeters:03d}_a{degrees:03d}",
                    "radius_m": millimeters / 1000,
                    "angle_degrees": degrees,
                    "state": state,
                }
            )
    return rows


def screen_supported_body(
    *,
    footprint_xy: Any,
    support_half_size: Any,
    contacts: list[dict[str, Any]],
    support_geom: str,
) -> dict[str, Any]:
    """Screen support/contact eligibility without certifying dynamics."""
    import numpy as np

    points = np.asarray(footprint_xy, dtype=float)
    half = np.asarray(support_half_size, dtype=float)
    if (
        points.ndim != 2
        or points.shape[1] != 2
        or not len(points)
        or not np.isfinite(points).all()
        or half.shape != (2,)
        or not np.isfinite(half).all()
        or (half <= FOOTPRINT_MARGIN_M).any()
    ):
        raise ValueError("finite corners and positive support inset required")
    if not isinstance(support_geom, str) or not support_geom:
        raise ValueError("named support required")
    reasons: list[str] = []
    support: list[float] = []
    others: list[str] = []
    if np.any(np.abs(points) > half - FOOTPRINT_MARGIN_M):
        reasons.append("outside_support_inset")
    for row in contacts:
        if set(row) != {"other_geom", "distance"}:
            raise ValueError("named distance contact records required")
        name, distance = row["other_geom"], row["distance"]
        if (
            not isinstance(name, str)
            or not name
            or isinstance(distance, bool)
            or not np.isscalar(distance)
            or not np.isfinite(distance)
        ):
            raise ValueError("finite named contact required")
        if name == support_geom:
            support.append(float(distance))
        else:
            others.append(name)
    if others:
        reasons.append("non_support_contact")
    if not support or min(support) > 0:
        reasons.append("no_nonpositive_support_contact")
    if support and min(support) < -MAX_SUPPORT_PENETRATION_M:
        reasons.append("excess_support_penetration")
    return {
        "physical_valid": not reasons,
        "reasons": reasons,
        "min_support_distance": min(support) if support else None,
        "non_support_geoms": sorted(set(others)),
        "footprint_margin_m": FOOTPRINT_MARGIN_M,
        "max_support_penetration_m": MAX_SUPPORT_PENETRATION_M,
    }
