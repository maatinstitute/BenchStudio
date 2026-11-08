"""Native objects/endpoint functions are synthetic; no provider or GPU imports."""
import asyncio
from functools import partial
import json
from pathlib import Path
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

import benchstudio as bs


def benchmark(inputs, targets, scorer):
    return bs.Benchmark("native", "data-r1", inputs, targets, scorer, "scorer-r1")


def test_native_parameters_and_raw_outputs_pass_through_without_schema(tmp_path, monkeypatch):
    parameters = SimpleNamespace(future_upstream_feature="custom-value")
    calls, scored = [], []
    class NativeEngine:
        def generate(self, prompts, sampling_params, *, future_engine_option):
            assert sampling_params is parameters
            calls.append((prompts, future_engine_option))
            return [SimpleNamespace(native_text=prompt.upper(), internal_data=object()) for prompt in prompts]
    engine = NativeEngine()
    infer = partial(engine.generate, sampling_params=parameters, future_engine_option=123)
    monkeypatch.setattr("importlib.metadata.version", lambda name: "future-version")
    system = bs.System.from_callable(infer, name="native-engine", revision="full-config-r1",
        batched=True, dependencies=("native-provider",),
        configuration={"sampling": {"future_upstream_feature": "custom-value"}, "future_engine_option": 123})
    def score(output, target):
        scored.append(output)
        return bs.Score(output.native_text == target)
    evaluation = bs.pipeline(system=system, benchmark=benchmark(["a", "b", "c"], ["A", "B", "C"], score),
        config=bs.EvaluationConfig(batch_size=2, output_dir=tmp_path / "out"))
    assert evaluation.check().configuration_valid and not calls
    result = evaluation()
    assert calls == [(["a", "b"], 123), (["c"], 123)]
    assert len(scored) == 3 and all(trial.success for trial in result.trials)
    retained = bs.open_run(tmp_path / "out")
    assert retained.system.metadata["distributions"]["native-provider"] == "future-version"
    assert retained.system.metadata["configuration"]["values"]["future_engine_option"] == 123


def test_endpoint_configuration_is_declared_and_never_modified(tmp_path):
    calls = []
    request = {"model": "caller-model", "temperature": .75, "new_server_option": True}
    def infer(prompt):
        calls.append(dict(request))
        return SimpleNamespace(native_payload=prompt)
    system = bs.System.from_callable(infer, name="remote-system", revision="request-r1",
        configuration={"endpoint": "https://example.invalid/inference", "request": request})
    assert system.describe()["configuration"]["values"]["request"] == request
    evaluation = bs.pipeline(system=system, benchmark=benchmark(["a"], ["a"],
        lambda output, target: bs.Score(output.native_payload == target)),
        config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    assert evaluation().trials[0].success
    assert calls == [request]
    record = json.loads((tmp_path / "out/system.json").read_text())
    assert record["metadata"]["configuration"]["values"]["endpoint"] == "https://example.invalid/inference"


def test_opaque_configuration_is_explicit_and_scalar_native_calls_work():
    calls = []
    system = bs.System.from_callable(lambda prompts: calls.append(prompts) or [object()],
                                    name="opaque-native", revision="r1", batched=True)
    assert system.describe()["configuration"] == {"status": "opaque"}
    value = system.runtime("a")
    assert value is not None and calls == [["a"]]


def test_declared_configuration_mutation_refuses_before_execution_or_output(tmp_path):
    configuration = {"temperature": .2}
    system = bs.System.from_callable(lambda value: pytest.fail("called"), name="endpoint", revision="r1",
                                    configuration=configuration)
    configuration["temperature"] = .9
    evaluation = bs.pipeline(system=system, benchmark=benchmark([1], [1], lambda a, b: bs.Score()),
                            config=bs.EvaluationConfig(output_dir=tmp_path / "out"))
    assert not evaluation.check().configuration_valid
    with pytest.raises(TypeError, match="configuration changed"):
        evaluation()
    assert not (tmp_path / "out").exists()
    assert system.describe()["configuration"]["values"]["temperature"] == .2


@pytest.mark.parametrize("output", [[], [1, 2], "text", {"response": 1}])
def test_batch_shape_errors_do_not_reach_scoring(output):
    system = bs.System.from_callable(lambda values: output, name="native", revision="r1", batched=True)
    evaluation = bs.pipeline(system=system, benchmark=benchmark([1], [1],
        lambda a, b: pytest.fail("scored invalid batch")), config=bs.EvaluationConfig(batch_size=1))
    with pytest.raises((TypeError, ValueError)):
        evaluation()


def test_async_scalar_configuration_preserves_async_contract():
    async def runtime(value):
        return value * 2
    system = bs.System.from_callable(runtime, name="async-native", revision="r1", configuration={"caller": True})
    evaluation = bs.pipeline(system=system, benchmark=benchmark([1], [2], lambda a, b: bs.Score(a == b)))
    assert not evaluation.check().configuration_valid
    assert asyncio.run(evaluation.arun()).trials[0].success
    with pytest.raises(TypeError, match="synchronous"):
        bs.System.from_callable(runtime, name="bad", revision="r1", batched=True)


def test_native_versions_and_declared_settings_change_identity(monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda name: "first")
    first = bs.System.from_callable(lambda x: x, name="native", revision="r1", dependencies=("provider",))
    monkeypatch.setattr("importlib.metadata.version", lambda name: "second")
    second = bs.System.from_callable(lambda x: x, name="native", revision="r1", dependencies=("provider",))
    third = bs.System.from_callable(lambda x: x, name="native", revision="r1", configuration={"model": "other"})
    assert len({first.spec.digest, second.spec.digest, third.spec.digest}) == 3


def test_vla_observations_and_actions_are_not_treated_as_text():
    observation = SimpleNamespace(camera=object(), proprioception=(.1, .2, .3))
    action = SimpleNamespace(chunk=((.1, .2, .3, .4, .5, .6, -1),), units="controller-native")
    class Policy:
        def select_action(self, inputs):
            assert inputs is observation
            return action
    system = bs.System.from_callable(Policy().select_action, name="native-vla", revision="policy-stack-r1",
        configuration={"checkpoint_revision": "caller-checkpoint-r1", "controller": "caller-controller"})
    def score(output, target):
        assert output is action and target is action
        return bs.Score(metrics={"offline_action_error": 0.0})
    result = bs.pipeline(system=system, benchmark=benchmark([observation], [action], score))()
    assert result.trials[0].metrics["offline_action_error"] == 0.0
    assert result.trials[0].success is None  # No simulator-outcome claim.


def test_world_model_native_outputs_reach_scorer_unchanged():
    inputs = SimpleNamespace(history=(object(), object()), actions=((1, 2),))
    prediction = SimpleNamespace(frames=(object(),), latent_state=object())
    system = bs.System.from_callable(lambda value: prediction if value is inputs else None,
                                    name="world-model", revision="predictor-r1")
    def score(output, target):
        assert output is prediction
        return bs.Score(metrics={"prediction_fixture_error": 0.0})
    result = bs.pipeline(system=system, benchmark=benchmark([inputs], [None], score))()
    assert result.trials[0].success is None


def test_core_and_vla_binding_work_with_all_model_provider_imports_blocked():
    source = Path(__file__).resolve().parents[1] / "src"
    code = '''
import importlib.abc
import sys
class BlockProviders(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"vllm", "transformers", "openai", "torch", "jax"}:
            raise ImportError("provider import forbidden: " + fullname)
sys.meta_path.insert(0, BlockProviders())
import benchstudio as bs
system = bs.System.from_callable(lambda observation: (observation, 0.5),
    name="synthetic-vla", revision="r1", configuration={"policy": "caller-owned"})
benchmark = bs.Benchmark("observations", "r1", [7], [(7, 0.5)],
    lambda action, target: bs.Score(metrics={"error": float(action != target)}), "r1")
result = bs.pipeline(system=system, benchmark=benchmark)()
assert result.trials[0].metrics["error"] == 0.0
'''
    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True,
                   env={**os.environ, "PYTHONPATH": str(source)})
