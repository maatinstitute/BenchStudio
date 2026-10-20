import xml.etree.ElementTree as ET
from pathlib import Path

from scripts.prepare_urdf_studio_robot import prepare_robot


def test_prepare_robot_keeps_only_visual_matching_finger_collisions(tmp_path):
    source = tmp_path / "source.urdf"
    source.write_text(
        """<robot name="so101">
  <link name="arm"><collision><geometry><mesh filename="assets/arm.stl"/></geometry></collision></link>
  <link name="gripper_link">
    <visual><geometry><mesh filename="assets/wrist_roll_follower_so101_v1.stl"/></geometry></visual>
    <collision><geometry><mesh filename="assets/servo.stl"/></geometry></collision>
    <collision><origin xyz="0 0 1"/><geometry><mesh filename="assets/wrist_roll_follower_so101_v1.stl"/></geometry></collision>
  </link>
  <link name="moving_jaw_so101_v1_link">
    <visual><geometry><mesh filename="assets/moving_jaw_so101_v1.stl"/></geometry></visual>
    <collision><origin xyz="0 0 2"/><geometry><mesh filename="assets/moving_jaw_so101_v1.stl"/></geometry></collision>
  </link>
  <joint name="gripper" type="revolute"><parent link="gripper_link"/><child link="moving_jaw_so101_v1_link"/></joint>
</robot>""",
        encoding="utf-8",
    )
    output = tmp_path / "staged.urdf"

    prepare_robot(source, output, damping=1.5)

    root = ET.parse(output).getroot()
    collisions = root.findall(".//collision")
    assert [collision.get("name") for collision in collisions] == [
        "fixed_finger_contact_mesh",
        "moving_finger_contact_mesh",
    ]
    assert [
        Path(collision.find("./geometry/mesh").get("filename")).name
        for collision in collisions
    ] == ["wrist_roll_follower_so101_v1.stl", "moving_jaw_so101_v1.stl"]
    assert [collision.find("origin").get("xyz") for collision in collisions] == [
        "0 0 1",
        "0 0 2",
    ]
    dynamics = root.find("./joint/dynamics")
    assert dynamics is not None
    assert dynamics.get("damping") == "1.5"
    assert dynamics.get("friction") == "0.02"
