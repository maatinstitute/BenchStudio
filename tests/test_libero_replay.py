import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from benchstudio.libero import LiberoAdapter, replay_libero


class NativeEnv:
    def __init__(self, *, changed=False, **_):
        self.changed = changed
        self.closed = False
        self.calls = []
        self.env = SimpleNamespace(sim=SimpleNamespace(get_state=self.state))

    def state(self):
        return SimpleNamespace(flatten=lambda: [self.tick])

    def seed(self, seed):
        self.calls.append(("seed", seed))

    def reset(self):
        self.tick = 0
        self.calls.append(("reset",))

    def set_init_state(self, state):
        self.calls.append(("restore", state))
        return {"image": [0]}

    def step(self, action):
        self.tick += 1
        return {"image": [int(self.changed)]}, 0.0, False, {}

    def check_success(self):
        return False

    def close(self):
        self.closed = True


class LiberoReplayTests(unittest.TestCase):
    def test_replay_reports_first_changed_frame_and_closes_fresh_environments(self):
        instances = []

        def factory(**kwargs):
            env = NativeEnv(changed=len(instances) == 2, **kwargs)
            instances.append(env)
            return env

        root, package, envs = (ModuleType(name) for name in (
            "libero", "libero.libero", "libero.libero.envs"
        ))
        suite = SimpleNamespace(
            tasks=["fixture"],
            get_task_init_states=lambda _: ["saved-state"],
            get_task=lambda _: SimpleNamespace(problem_folder="suite", bddl_file="task.bddl"),
        )
        package.benchmark = SimpleNamespace(get_benchmark_dict=lambda: {"libero_object": lambda: suite})
        package.get_libero_path = lambda _: "/fixture/assets"
        envs.OffScreenRenderEnv = factory
        modules = {module.__name__: module for module in (root, package, envs)}
        with patch.dict(sys.modules, modules):
            adapter = LiberoAdapter("libero_object", task_id=0, seed=42)
            reference = adapter.capture([[0.0]])
            self.assertTrue(replay_libero(reference)["passed"])
            changed = adapter.replay(reference)
        self.assertEqual(changed["first_mismatch_step"], 1)
        self.assertEqual(changed["differences"][0]["observation_fields"], ["image"])
        self.assertNotIn("qualification_fixture", changed)
        for instance in instances:
            self.assertTrue(instance.closed)
            self.assertEqual(instance.calls, [("seed", 42), ("reset",), ("restore", "saved-state")])

    def test_invalid_reference_or_action_fails_before_loading_libero(self):
        adapter = LiberoAdapter("libero_object", task_id=0)
        with self.assertRaisesRegex(ValueError, "finite numeric"):
            adapter.capture([[float("nan")]])
        with self.assertRaisesRegex(ValueError, "does not match"):
            adapter.replay({"schema": "wrong"})

    def test_lerobot_replay_uses_raw_reset_and_step(self):
        native = NativeEnv()
        native.env.sim.forward = lambda: None
        native.env._get_observations = lambda *, force_update: {"image": [0]}
        owner = SimpleNamespace(
            _env=native, reset=lambda *, seed: (native.seed(seed), native.reset()),
            close=native.close,
        )
        names = ("libero", "libero.libero", "lerobot", "lerobot.envs",
                 "lerobot.envs.libero", "numpy")
        modules = {name: ModuleType(name) for name in names}
        suite = SimpleNamespace(tasks=["fixture"], get_task_init_states=lambda _: ["state"])
        modules["libero.libero"].benchmark = SimpleNamespace(
            get_benchmark_dict=lambda: {"libero_object": lambda: suite}
        )
        modules["libero.libero"].get_libero_path = lambda _: "/fixture/assets"
        modules["lerobot.envs.libero"].LiberoEnv = lambda *args, **kwargs: owner
        modules["numpy"].asarray = lambda vector: vector
        with patch.dict(sys.modules, modules):
            adapter = LiberoAdapter("libero_object", task_id=0, seed=42, backend="lerobot")
            reference = adapter.capture([[0.0]])
        self.assertEqual(owner.init_state_id, 0)
        self.assertEqual(native.calls, [("seed", 42), ("reset",)])
        self.assertEqual(len(reference["frames"]), 2)
        self.assertTrue(native.closed)
