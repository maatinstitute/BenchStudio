#!/usr/bin/env python3
"""Prepare an upstream URDF Studio robot for a controlled MuJoCo episode.

The source SO-101 simulation URDF has dense whole-robot mesh collisions and no
declared joint damping. For this diagnostic fixture, the staging transform
retains only the two exact finger-mesh collisions that correspond to rendered
geometry and adds reviewable joint damping. Visual geometry, kinematics,
limits, and the upstream checkout remain unchanged.
"""

from __future__ import annotations

import argparse
import copy
import xml.etree.ElementTree as ET
from pathlib import Path


def prepare_robot(source: Path, output: Path, damping: float) -> None:
    tree = ET.parse(source)
    root = tree.getroot()
    retained_collisions: dict[str, ET.Element] = {}
    for link in root.findall("link"):
        link_name = str(link.get("name"))
        for collision in link.findall("collision"):
            mesh = collision.find("./geometry/mesh")
            filename = str(mesh.get("filename", "")) if mesh is not None else ""
            if (
                link_name == "gripper_link"
                and filename.endswith("wrist_roll_follower_so101_v1.stl")
            ):
                retained_collisions["fixed_finger_contact_mesh"] = copy.deepcopy(collision)
            elif (
                link_name == "moving_jaw_so101_v1_link"
                and filename.endswith("moving_jaw_so101_v1.stl")
            ):
                retained_collisions["moving_finger_contact_mesh"] = copy.deepcopy(collision)
            link.remove(collision)
    collision_links = {
        "gripper_link": "fixed_finger_contact_mesh",
        "moving_jaw_so101_v1_link": "moving_finger_contact_mesh",
    }
    for link in root.findall("link"):
        collision_name = collision_links.get(str(link.get("name")))
        if collision_name is None:
            continue
        collision = retained_collisions.get(collision_name)
        if collision is None:
            raise ValueError(f"source URDF is missing {collision_name}")
        collision.set("name", collision_name)
        mesh = collision.find("./geometry/mesh")
        if mesh is not None:
            mesh_path = Path(str(mesh.get("filename")))
            if not mesh_path.is_absolute():
                mesh.set("filename", str((source.parent / mesh_path).resolve()))
        link.append(collision)
    for joint in root.findall("joint"):
        if joint.get("type") not in {"revolute", "continuous", "prismatic"}:
            continue
        dynamics = joint.find("dynamics")
        if dynamics is None:
            dynamics = ET.SubElement(joint, "dynamics")
        dynamics.set("damping", f"{damping:g}")
        dynamics.set("friction", "0.02")
    output.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--damping", type=float, default=1.5)
    args = parser.parse_args()
    prepare_robot(args.source, args.output, args.damping)
    print(f"prepared_robot={args.output} damping={args.damping:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
