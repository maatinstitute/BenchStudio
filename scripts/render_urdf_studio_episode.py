#!/usr/bin/env python3
"""Render a recorded URDF Studio episode through its native MuJoCo backend.

URDF Studio's portable episode video is intentionally a schematic object view.
This connector rebuilds the exact staged scenario with the upstream backend and
replays its recorded joint/object states, so BenchStudio can show the robot
without owning a second robot model or simulation implementation.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def _trace_frames(path: Path) -> list[tuple[int, dict, dict]]:
    by_time: dict[int, dict[str, dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        stream = record.get("stream")
        if stream not in {"robot_joints", "objects"}:
            continue
        t_ms = int(record.get("t_ms", 0))
        by_time.setdefault(t_ms, {})[stream] = record.get("state", {})
    frames = []
    for t_ms, streams in sorted(by_time.items()):
        joints = streams.get("robot_joints", {}).get("joint_positions", {})
        objects = streams.get("objects", {})
        if joints and objects:
            frames.append((t_ms, joints, objects))
    return frames


def render_episode(
    scenario_path: Path,
    manifest_path: Path,
    trace_path: Path,
    output_path: Path,
) -> None:
    import imageio.v2 as imageio
    import mujoco

    from backend.models.scenario import EpisodeManifest
    from backend.scripts.scenario_episode_worker import _build_backend
    from backend.services.scenario_loader import load_scenario
    from backend.services.sim_backends.types import ObjectPose, SimState

    manifest = EpisodeManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    frames = _trace_frames(trace_path)
    if not frames:
        raise ValueError(f"No replayable frames in {trace_path}")

    with tempfile.TemporaryDirectory(prefix="benchstudio-robot-render-") as temp_dir:
        visual_scenario_dir = Path(temp_dir) / "scenario"
        shutil.copytree(scenario_path.parent, visual_scenario_dir)
        visual_scenario_path = visual_scenario_dir / scenario_path.name
        scenario = load_scenario(str(visual_scenario_path))
        if not scenario.robot.urdf:
            raise ValueError("The scenario does not declare a robot URDF")
        robot_path = visual_scenario_dir / scenario.robot.urdf
        tree = ET.parse(robot_path)
        mujoco_extension = ET.SubElement(tree.getroot(), "mujoco")
        ET.SubElement(mujoco_extension, "compiler", {"discardvisual": "false"})
        tree.write(robot_path, encoding="utf-8", xml_declaration=True)

        previous_cwd = Path.cwd()
        try:
            os.chdir(visual_scenario_dir)
            backend = _build_backend("mujoco", scenario, str(visual_scenario_path))
            backend.load_scene(physics_timestep_s=scenario.runtime.physics_timestep_s)
            backend.reset_episode(manifest)
        finally:
            os.chdir(previous_cwd)

        renderer = mujoco.Renderer(backend._model, height=360, width=640)
        camera = mujoco.MjvCamera()
        camera.lookat[:] = (0.20, 0.0, 0.13)
        camera.distance = 0.66
        camera.azimuth = 105.0
        camera.elevation = -16.0

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with imageio.get_writer(str(output_path), fps=20, macro_block_size=None) as writer:
            for t_ms, joints, objects in frames:
                backend.set_state(
                    SimState(
                        sim_time_s=t_ms / 1000.0,
                        joint_positions={str(k): float(v) for k, v in joints.items()},
                        joint_velocities={},
                        object_poses={
                            str(object_id): ObjectPose(
                                position_xyz=tuple(float(v) for v in pose["position_xyz"]),
                                quat_wxyz=tuple(float(v) for v in pose["quat_wxyz"]),
                            )
                            for object_id, pose in objects.items()
                        },
                    )
                )
                renderer.update_scene(backend._data, camera=camera)
                writer.append_data(renderer.render())
        renderer.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    render_episode(args.scenario, args.manifest, args.trace, args.output)
    print(f"robot_video={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
