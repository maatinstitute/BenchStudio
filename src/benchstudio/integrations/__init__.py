"""Optional integration boundaries loaded only when explicitly requested."""

from __future__ import annotations

from importlib import import_module

_MODULES = (
    "alpabridge", "alpabridge_camera_calibration", "alpabridge_contract",
    "alpabridge_image", "alpabridge_inference_cache", "alpabridge_lifecycle",
    "alpabridge_policy_registry", "alpabridge_route", "alpabridge_signal",
    "alpabridge_trajectory_selector", "alpasim_metrics", "genesis", "gymnasium",
    "isaaclab", "mujoco", "policy_trace", "replay_conformance", "robochallenge",
    "robopad_cell_store", "robopad_competence", "robopad_evidence_codec",
    "robopad_evidence_store", "robopad_initialization", "robopad_reference",
    "robopad_reference_adapter", "robopad_reference_cache", "robopad_remaining",
    "robopad_rollout", "robopad_state_evidence", "robopad_supervisor",
    "smolvla_driving_contract", "teleop_replay_timing", "urdf_world_bridge",
    "worldepisode",
)


def __getattr__(name: str):
    for module_name in _MODULES:
        module = import_module(f".{module_name}", __name__)
        if hasattr(module, name):
            value = getattr(module, name)
            globals()[name] = value
            return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    names = set(globals())
    for module_name in _MODULES:
        try:
            module = import_module(f".{module_name}", __name__)
        except ImportError:
            continue
        names.update(name for name in vars(module) if not name.startswith("_"))
    return sorted(names)

