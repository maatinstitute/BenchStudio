#!/usr/bin/env python3
"""Prepare an upstream URDF Studio robot for a controlled MuJoCo episode.

The source SO-101 URDF intentionally describes geometry and limits but does
not declare joint damping. URDF Studio's position actuators therefore ring in
MuJoCo. This staging transform adds explicit, reviewable damping without
modifying the upstream checkout or changing robot geometry and limits.
"""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def prepare_robot(source: Path, output: Path, damping: float) -> None:
    tree = ET.parse(source)
    root = tree.getroot()
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
