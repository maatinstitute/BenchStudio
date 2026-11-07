import pytest

from benchstudio.system_spec import Component, Connection, SystemSpec


def system():
    return SystemSpec(
        "collaborative-picking", "r1",
        components=(
            Component("world", "world_model", "custom/world", "a1",
                      inputs=("camera",), outputs=("predicted_state",)),
            Component("planner", "agent", "planner", "v2",
                      inputs=("world", "feedback"), outputs=("plan",)),
            Component("robot", "controller", "robot", "v1",
                      inputs=("action",), outputs=("feedback",)),
            Component("translator", "world_action_model", "wam", "v3",
                      inputs=("plan",), outputs=("action",)),
        ),
        connections=(
            Connection("world", "predicted_state", "planner", "world"),
            Connection("planner", "plan", "translator", "plan"),
            Connection("translator", "action", "robot", "action"),
            Connection("robot", "feedback", "planner", "feedback"),
        ),
    )


def test_composite_feedback_graph_roundtrip_digest_is_stable():
    spec = system()
    assert SystemSpec.from_dict(spec.to_dict()).digest == spec.digest
    assert len(spec.components) == 4
    assert len(spec.connections) == 4


def test_versioned_node_changes_system_identity():
    before = system().to_dict()
    before["components"][1]["revision"] = "v3"
    assert SystemSpec.from_dict(before).digest != system().digest


def test_unknown_node_or_port_fails_closed():
    data = system().to_dict()
    data["connections"][0]["target"] = "missing"
    with pytest.raises(ValueError, match="unknown component"):
        SystemSpec.from_dict(data)
    data = system().to_dict()
    data["connections"][0]["source_port"] = "not-a-real-port"
    with pytest.raises(ValueError, match="unknown output"):
        SystemSpec.from_dict(data)


def test_duplicate_nodes_and_invalid_metadata_rejected():
    c = Component("agent", "agent", "test", "v1")
    with pytest.raises(ValueError, match="duplicate component"):
        SystemSpec("s", "v1", components=(c, c))
    with pytest.raises(ValueError, match="canonical"):
        SystemSpec("s", "v1", components=(c,), metadata={"bad": float("nan")})


def test_zero_extra_framework_requirements_for_single_policy():
    spec = SystemSpec("single", "v1",
                      components=(Component("vla", "vla", "smolvla", "v2"),))
    assert spec.digest



def test_nested_metadata_cannot_change_system_identity_after_construction():
    metadata = {"nested": {"values": [1, 2]}}
    spec = SystemSpec("s", "r1", (Component("a", "agent", "a", "r1"),), metadata=metadata)
    digest = spec.digest
    metadata["nested"]["values"].append(3)
    exported = spec.to_dict()
    exported["metadata"]["nested"]["values"].append(4)
    with pytest.raises(TypeError):
        spec.metadata["nested"]["values"] = ()
    assert spec.digest == digest
    assert SystemSpec.from_dict(spec.to_dict()).digest == digest


def test_immutable_identity_is_computed_once_and_export_is_independent():
    from unittest.mock import patch
    import benchstudio.system_spec as module
    spec = system()
    with patch.object(module, "_canonical", wraps=module._canonical) as encode:
        first = spec.digest
        assert spec.digest == first
        assert encode.call_count == 1
    exported = spec.to_dict()
    exported["components"][0]["revision"] = "changed"
    assert spec.digest == first
    assert SystemSpec.from_dict(exported).digest != first
