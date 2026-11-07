"""Synthetic system-comparison demonstration. Does NOT execute a robot."""
import benchstudio as bs

base = bs.SystemSpec("planning-stack", "r1", (
    bs.Component("world", "world_model", "latent-world", "v1"),
    bs.Component("agent", "agent", "planner", "stable"),
    bs.Component("actor", "vla", "robot-policy", "frozen"),
))
candidate = bs.SystemSpec("planning-stack", "r2", (
    bs.Component("world", "world_model", "latent-world", "v2"),
    bs.Component("agent", "agent", "planner", "stable"),
    bs.Component("actor", "vla", "robot-policy", "frozen"),
))
records = {}
for name, system, outcomes in [
    ("baseline", base, (False, True, False, True)),
    ("candidate", candidate, (True, True, False, True)),
]:
    trials = []
    for seed, success in enumerate(outcomes):
        unit = bs.TrialKey(
            "pick", "task-v1", "sceneA", "nominal", seed, 0,
            "mujoco-v1", "a" * 64, "native-checker", "r1",
        )
        trials.append(bs.Trial(
            f"trial-{seed}", unit, system.digest, "completed", success,
            "declared", True,
        ))
    records[name] = bs.SystemRun(name, system, tuple(trials))
ablation = bs.audit_ablation(base, candidate, allowed_components=("world",))
comparison = bs.compare_system_runs(records["baseline"], records["candidate"])
print("Synthetic demonstration only: not measured model performance")
print("Graph change structurally isolated:", ablation.structurally_isolated)
print("Valid matched episodes:", comparison.valid_binary_pairs)
print("Paired success delta:", comparison.paired_success.success_gap_b_minus_a)
print("Evidence interpretation:", comparison.interpretation)
