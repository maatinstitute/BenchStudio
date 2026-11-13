from types import SimpleNamespace as NS

import numpy as np
import pytest

from reva.integrations import build_goals, extract_geometry


def _fixture():
    model = NS(
        body_name2id=lambda name: {"target": 0}.get(name, -1),
        site_name2id=lambda name: {"eef": 0, "basket_1_contain_region": 1}.get(name, -1),
        geom_name2id=lambda name: {
            "target_box": 0,
            "basket_1_g1": 1,
            **{f"basket_1_g{i}": 2 for i in range(2, 6)},
        }.get(name, -1),
        site_size=np.array([[0.01] * 3, [0.1, 0.1, 0.1]]),
        site_type=[6, 6],
        site_bodyid=[2, 1],
        geom_bodyid=[0, 1, 1],
        geom_type=[6, 6, 6],
        geom_size=np.array([[0.01] * 3, [0.01] * 3, [0.01] * 3]),
    )
    data = NS(
        body_xpos=np.array([[0.0, 0.0, 0.05]]),
        body_xmat=np.eye(3)[None],
        site_xpos=np.array([[0.02, 0.0, 0.08], [0.5, 0, 0.12]]),
        site_xmat=np.array([np.eye(3), np.eye(3)]),
        geom_xpos=np.array([[0.0, 0.0, 0.05], [0.5, 0.0, 0.01], [0.5, 0.0, 0.3]]),
        geom_xmat=np.array([np.eye(3), np.eye(3), np.eye(3)]),
    )
    controller = NS(
        control_dim=6,
        impedance_mode="fixed",
        use_delta=True,
        use_ori=True,
        input_min=np.full(6, -1),
        input_max=np.ones(6),
        output_min=np.array([-0.05] * 3 + [-0.5] * 3),
        output_max=np.array([0.05] * 3 + [0.5] * 3),
        position_limits=None,
        orientation_limits=None,
        interpolator_pos=None,
        interpolator_ori=None,
        eef_name="eef",
    )
    return NS(
        env=NS(
            robots=[NS(controller=controller, action_dim=7, has_gripper=True)],
            sim=NS(model=model, data=data),
        )
    )


def _extract(env):
    return extract_geometry(env, target_body="target", target_geoms=["target_box"])


def test_source_copy_offset_centering_and_frozen_goal_stages():
    env = _fixture()
    source = _extract(env)
    env.env.sim.data.body_xpos[0] = 9
    np.testing.assert_allclose(source.target_position, [0, 0, 0.05])
    goals = build_goals(source, source, source_held=False, clearance=0.05, wall_margin=0.005)
    np.testing.assert_allclose(goals.positions["release"], [0.52, 0, 0.15])
    reference = goals.controller(False)
    for stage, _duration, _waypoint, _gripper in reference.stages:
        position, rotation = goals.for_stage(stage)
        assert position.shape == (3,)
        assert rotation.shape == (3, 3)
    with pytest.raises(ValueError):
        goals.positions["release"][0] = 3
    position, _ = goals.for_stage("release")
    position[0] = 3
    assert goals.positions["release"][0] != 3
    assert goals.unresolved_checks


def test_bad_runtime_scale_missing_geometry_and_applicability_fail_closed():
    env = _fixture()
    env.env.robots[0].controller.output_max[0] = 0.1
    with pytest.raises(ValueError):
        _extract(env)
    with pytest.raises(ValueError):
        extract_geometry(_fixture(), target_body="missing", target_geoms=["target_box"])
    with pytest.raises(ValueError):
        extract_geometry(_fixture(), target_body="target", target_geoms=[])
    env = _fixture()
    env.env.sim.model.geom_size[0] = 0.2
    with pytest.raises(ValueError):
        build_goals(
            _extract(env), _extract(env), source_held=True, clearance=0.05, wall_margin=0.005
        )
    env = _fixture()
    env.env.sim.data.site_xmat[1] = np.diag([1, -1, -1])
    with pytest.raises(ValueError):
        build_goals(
            _extract(env), _extract(env), source_held=True, clearance=0.05, wall_margin=0.005
        )
    source = _extract(_fixture())
    with pytest.raises(ValueError):
        build_goals(source, source, source_held=True, clearance=-1, wall_margin=0.005)


def test_rotated_basket_height_and_tall_object_floor_clearance():
    env = _fixture()
    angle = np.pi / 6
    rotation = np.array(
        [[1, 0, 0], [0, np.cos(angle), -np.sin(angle)], [0, np.sin(angle), np.cos(angle)]]
    )
    env.env.sim.data.site_xmat[1] = rotation
    source = _extract(env)
    goals = build_goals(source, source, source_held=True, clearance=0.05, wall_margin=0.005)
    corners = np.array(
        [
            np.array([x, y, z]) * source.basket_half_size
            for x in (-1, 1)
            for y in (-1, 1)
            for z in (-1, 1)
        ]
    )
    highest = (corners @ rotation.T + source.basket_position)[:, 2].max()
    offset = source.eef_position - source.target_position
    target_bottom = goals.positions["above_basket"][2] - offset[2] - source.target_world_extent[2]
    assert target_bottom + 1e-12 >= highest + 0.05
    assert target_bottom + 1e-12 >= source.basket_collision_top_z + 0.05
    env = _fixture()
    env.env.sim.model.geom_size[0] = [0.01, 0.01, 0.105]
    tall = _extract(env)
    tall_goals = build_goals(tall, tall, source_held=True, clearance=0.05, wall_margin=0.005)
    release_center = tall_goals.positions["release"] - (tall.eef_position - tall.target_position)
    assert release_center[2] == pytest.approx(0.135)
    assert release_center[2] - tall.target_world_extent[2] > tall.basket_floor_top_z + 0.005
