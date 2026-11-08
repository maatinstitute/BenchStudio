"""Synthetic system-comparison demonstration. Does NOT execute a robot."""
import benchstudio as bs
from benchstudio.system_spec import Component, SystemSpec
from benchstudio.system_evidence import TrialKey, Trial, SystemRun
from benchstudio.system_ablations import audit_ablation
from benchstudio.system_comparison import compare_system_runs

base = SystemSpec("planning-stack", "r1", (
    Component("world", "world_model", "latent-world", "v1"),
    Component("agent", "agent", "planner", "stable"),
    Component("actor", "vla", "robot-policy", "frozen"),
))
candidate = SystemSpec("planning-stack", "r2", (
    Component("world", "world_model", "latent-world", "v2"),
    Component("agent", "agent", "planner", "stable"),
    Component("actor", "vla", "robot-policy", "frozen"),
))
records = {}
for name, system, outcomes in [
    ("baseline", base, (False, True, False, True)),
    ("candidate", candidate, (True, True, False, True)),
]:
    trials = []
    for seed, success in enumerate(outcomes):
        unit = TrialKey(
            "pick", "task-v1", "sceneA", "nominal", seed, 0,
            "mujoco-v1", "a" * 64, "native-checker", "r1",
        )
        trials.append(Trial(
            f"trial-{seed}", unit, system.digest, "completed", success,
            "declared", True,
        ))
    records[name] = SystemRun(name, system, tuple(trials))
ablation = audit_ablation(base, candidate, allowed_components=("world",))
comparison = compare_system_runs(records["baseline"], records["candidate"])
print("Synthetic demonstration only: not measured model performance")
print("Graph change structurally isolated:", ablation.structurally_isolated)
print("Valid matched episodes:", comparison.valid_binary_pairs)
print("Paired success delta:", comparison.paired_success.success_gap_b_minus_a)
print("Evidence interpretation:", comparison.interpretation)
