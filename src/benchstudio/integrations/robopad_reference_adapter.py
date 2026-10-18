"""Read-only RoboPAD source-geometry adapter; not a rollout or competence gate.

The caller supplies a separately restored diagnostic environment. This adapter
never resets, steps, forwards, updates a controller, or repairs stale state.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ..conformance.path_geometry import proper_rotation
from .robopad_reference import FixedReference


def _frozen(value: Any):
    import numpy as np

    result = np.array(value, dtype=float, copy=True)
    result.flags.writeable = False
    return result


def _vector(value: Any, shape: tuple[int, ...], name: str):
    import numpy as np

    result = np.asarray(value, dtype=float)
    if result.shape != shape or not np.isfinite(result).all():
        raise ValueError(f"invalid {name}")
    return result.copy()


def transfer_grasp(
    anchor_target_pos: Any,
    anchor_target_rotation: Any,
    anchor_eef_pos: Any,
    anchor_eef_rotation: Any,
    source_target_pos: Any,
    source_target_rotation: Any,
):
    """Transfer an end-effector grasp offset between target poses."""
    import numpy as np

    points = [
        np.asarray(point, dtype=float)
        for point in (anchor_target_pos, anchor_eef_pos, source_target_pos)
    ]
    if any(point.shape != (3,) or not np.isfinite(point).all() for point in points):
        raise ValueError("finite position vectors required")
    target0, eef0, target1 = points
    rotation0 = proper_rotation(anchor_target_rotation)
    rotation1 = proper_rotation(source_target_rotation)
    local_offset = rotation0.T @ (eef0 - target0)
    return target1 + rotation1 @ local_offset, rotation1 @ rotation0.T @ proper_rotation(
        anchor_eef_rotation
    )


@dataclass(frozen=True)
class SourceGeometry:
    target_position: Any
    target_rotation: Any
    eef_position: Any
    eef_rotation: Any
    basket_position: Any
    basket_rotation: Any
    basket_half_size: Any
    target_world_extent: Any
    basket_collision_top_z: float
    basket_floor_top_z: float


def _pose(data: Any, kind: str, index: int):
    import numpy as np

    return (
        _vector(getattr(data, kind + "_xpos")[index], (3,), kind + " position"),
        proper_rotation(np.asarray(getattr(data, kind + "_xmat")[index]).reshape(3, 3)).copy(),
    )


def extract_geometry(
    env: Any,
    *,
    target_body: str,
    target_geoms: Any,
    basket_site: str = "basket_1_contain_region",
    basket_geoms: Any = tuple(f"basket_1_g{i}" for i in range(1, 6)),
) -> SourceGeometry:
    """Inspect one restored source and extract controller/model geometry."""
    import numpy as np

    base = env.env
    if len(base.robots) != 1:
        raise ValueError("exactly one robot required")
    robot = base.robots[0]
    controller = robot.controller
    if (
        controller.control_dim != 6
        or robot.action_dim != 7
        or not robot.has_gripper
        or controller.impedance_mode != "fixed"
        or not controller.use_delta
        or not controller.use_ori
    ):
        raise ValueError("expected fixed delta six-axis OSC and one gripper action")
    for name, expected in (
        ("input_min", [-1] * 6),
        ("input_max", [1] * 6),
        ("output_min", [-0.05] * 3 + [-0.5] * 3),
        ("output_max", [0.05] * 3 + [0.5] * 3),
    ):
        actual = np.asarray(getattr(controller, name), dtype=float)
        if actual.shape != (6,) or not np.allclose(actual, expected, atol=1e-12, rtol=0):
            raise ValueError("controller scale mismatch: " + name)
    if controller.position_limits is not None or controller.orientation_limits is not None:
        raise ValueError("unexpected OSC goal limits")
    if controller.interpolator_pos is not None or controller.interpolator_ori is not None:
        raise ValueError("unexpected OSC interpolation")
    model, data = base.sim.model, base.sim.data

    def index(kind: str, name: str) -> int:
        identifier = getattr(model, kind + "_name2id")(name)
        if identifier < 0:
            raise ValueError(f"missing {kind}: {name}")
        return identifier

    target_id, basket_site_id = index("body", target_body), index("site", basket_site)
    target_position, target_rotation = _pose(data, "body", target_id)
    eef_position, eef_rotation = _pose(data, "site", index("site", controller.eef_name))
    basket_position, basket_rotation = _pose(data, "site", basket_site_id)
    basket_half_size = _vector(model.site_size[basket_site_id], (3,), "basket half-size")
    if model.site_type[basket_site_id] != 6 or (basket_half_size <= 0).any():
        raise ValueError("positive box containment site required")
    names = tuple(target_geoms)
    if not names or len(set(names)) != len(names):
        raise ValueError("unique target collision box names required")
    target_extent = np.zeros(3)
    for name in names:
        geometry_id = index("geom", name)
        if model.geom_bodyid[geometry_id] != target_id or model.geom_type[geometry_id] != 6:
            raise ValueError("target geometry must be a box on specified target body")
        half = _vector(model.geom_size[geometry_id], (3,), "target box size")
        if (half <= 0).any():
            raise ValueError("positive target box size required")
        geometry_position, geometry_rotation = _pose(data, "geom", geometry_id)
        target_extent = np.maximum(
            target_extent,
            np.abs(geometry_position - target_position) + np.abs(geometry_rotation) @ half,
        )
    basket_names = tuple(basket_geoms)
    if not basket_names or len(set(basket_names)) != len(basket_names):
        raise ValueError("unique basket collision box names required")
    tops = []
    floor_top = None
    for name in basket_names:
        geometry_id = index("geom", name)
        if (
            model.geom_type[geometry_id] != 6
            or model.geom_bodyid[geometry_id] != model.site_bodyid[basket_site_id]
        ):
            raise ValueError("basket collision box must belong to containment-site body")
        half = _vector(model.geom_size[geometry_id], (3,), "basket collision box")
        if (half <= 0).any():
            raise ValueError("positive basket collision box sizes required")
        geometry_position, geometry_rotation = _pose(data, "geom", geometry_id)
        tops.append(float(geometry_position[2] + (np.abs(geometry_rotation) @ half)[2]))
        if name == "basket_1_g1":
            floor_top = tops[-1]
    if floor_top is None:
        raise ValueError("pinned basket floor geometry missing")
    return SourceGeometry(
        *(
            _frozen(value)
            for value in (
                target_position,
                target_rotation,
                eef_position,
                eef_rotation,
                basket_position,
                basket_rotation,
                basket_half_size,
                target_extent,
            )
        ),
        max(tops),
        floor_top,
    )


@dataclass(frozen=True)
class CandidateGoals:
    positions: Any
    orientations: Any
    unresolved_checks: tuple[str, ...]

    def for_stage(self, stage: str):
        names = {
            "open": "start",
            "approach": "above_target",
            "descend": "grasp",
            "close": "grasp",
            "lift": "lift",
            "transport": "above_basket",
            "lower": "release",
            "release": "release",
            "withdraw": "withdraw",
        }
        if stage not in names:
            raise ValueError("unknown or exhausted stage")
        key = names[stage]
        return self.positions[key].copy(), self.orientations[key].copy()

    def controller(self, source_held: bool) -> FixedReference:
        return FixedReference(
            source_held,
            self.positions,
            translation_scale=[0.05] * 3,
            rotation_scale=[0.5] * 3,
        )


def build_goals(
    source: SourceGeometry,
    anchor: SourceGeometry,
    *,
    source_held: bool,
    clearance: float,
    wall_margin: float,
) -> CandidateGoals:
    """Build fixed source-derived goals with explicit applicability margins."""
    import numpy as np

    if type(source_held) is not bool:
        raise ValueError("explicit possession required")
    if not np.isfinite([clearance, wall_margin]).all() or clearance <= 0 or wall_margin <= 0:
        raise ValueError("positive finite global margins required")
    for geometry in (source, anchor):
        for name in (
            "target_position",
            "eef_position",
            "basket_position",
            "basket_half_size",
            "target_world_extent",
        ):
            _vector(getattr(geometry, name), (3,), name)
        for name in ("target_rotation", "eef_rotation", "basket_rotation"):
            proper_rotation(getattr(geometry, name))
    if (source.basket_half_size <= 0).any() or (source.target_world_extent <= 0).any():
        raise ValueError("positive geometry extents required")
    if not np.isfinite(source.basket_collision_top_z):
        raise ValueError("finite basket collision height required")
    if source.basket_rotation[2, 2] <= 0:
        raise ValueError("sideways/inverted basket unsupported by fixed candidate")
    bounds = np.abs(source.basket_rotation.T) @ source.target_world_extent
    if (bounds[:2] + wall_margin >= source.basket_half_size[:2]).any():
        raise ValueError("target does not fit conservative containment bounds")
    if source_held:
        grasp, desired = source.eef_position.copy(), source.eef_rotation.copy()
    else:
        grasp, desired = transfer_grasp(
            anchor.target_position,
            anchor.target_rotation,
            anchor.eef_position,
            anchor.eef_rotation,
            source.target_position,
            source.target_rotation,
        )
    offset = grasp - source.target_position
    if not np.isfinite(source.basket_floor_top_z):
        raise ValueError("finite pinned floor height required")
    target_release = source.basket_position.copy()
    target_release[2] = max(
        target_release[2],
        source.basket_floor_top_z + source.target_world_extent[2] + 2 * wall_margin,
    )
    center_local = source.basket_rotation.T @ (target_release - source.basket_position)
    if (np.abs(center_local) + wall_margin >= source.basket_half_size).any():
        raise ValueError("floor-clear release center outside placement region")
    if (np.abs(center_local[:2]) + bounds[:2] + wall_margin >= source.basket_half_size[:2]).any():
        raise ValueError("floor-clear object exceeds lateral placement bounds")
    release = target_release + offset
    z = (
        max(
            source.target_position[2] + source.target_world_extent[2],
            source.basket_position[2]
            + (np.abs(source.basket_rotation) @ source.basket_half_size)[2],
            source.basket_collision_top_z,
        )
        + clearance
        + source.target_world_extent[2]
    )
    lift = grasp.copy()
    lift[2] = z + offset[2]
    above = release.copy()
    above[2] = lift[2]
    approach = grasp + [0, 0, clearance]
    positions = dict(
        start=source.eef_position,
        above_target=approach,
        grasp=grasp,
        lift=lift,
        above_basket=above,
        release=release,
        withdraw=above,
    )
    orientations = {key: desired for key in positions}
    orientations["start"] = source.eef_rotation
    return CandidateGoals(
        MappingProxyType({key: _frozen(value) for key, value in positions.items()}),
        MappingProxyType({key: _frozen(value) for key, value in orientations.items()}),
        (
            "source state/derived-pose synchronization and model hashes",
            "target geometry completeness and actual basket wall/path clearance",
            "live orientation goal initialization and zero-delta semantics",
            "live gripper sign, grasp applicability and controller competence",
        ),
    )
