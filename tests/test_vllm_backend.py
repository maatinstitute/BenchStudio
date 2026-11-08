import sys
import types
from unittest.mock import patch
import pytest
import benchstudio as bs


SHA = "a" * 40


def fake_vllm():
    calls = {"loads": [], "batches": [], "sampling": []}
    class Params:
        def __init__(self, **kwargs):
            calls["sampling"].append(kwargs)
    class Engine:
        def __init__(self, **kwargs):
            calls["loads"].append(kwargs)
        def generate(self, prompts, params, **kwargs):
            calls["batches"].append((list(prompts), kwargs))
            return [types.SimpleNamespace(prompt=p, outputs=[types.SimpleNamespace(text=p.upper())]) for p in prompts]
    return types.SimpleNamespace(LLM=Engine, SamplingParams=Params), calls


def test_lazy_persistent_loading_and_actual_backend_batches():
    module, calls = fake_vllm()
    with patch.dict(sys.modules, {"vllm": module}), patch("benchstudio.vllm_backend.version", return_value="0.33.0"), patch("benchstudio.backend_loading.metadata.version", return_value="0.33.0"):
        system = bs.System.from_pretrained("org/model", revision=SHA)
        data = bs.Benchmark("text", "r1", ["a", "b", "c"], ["A", "B", "C"],
                            lambda a,b: bs.Score(a == b), "r1")
        pipeline = bs.pipeline("system-evaluation", system=system, benchmark=data)
        assert calls["loads"] == []
        results = pipeline(batch_size=2)
        assert all(t.success for t in results.trials)
        assert len(calls["loads"]) == 1
        assert [b[0] for b in calls["batches"]] == [["a", "b"], ["c"]]
        assert system.runtime("d") == "D"
        assert len(calls["loads"]) == 1
        assert calls["loads"][0]["revision"] == calls["loads"][0]["tokenizer_revision"] == SHA
        assert calls["loads"][0]["trust_remote_code"] is False
        assert calls["loads"][0]["generation_config"] == "vllm"
        assert [t.trial_id for t in results.trials] == ["0", "1", "2"]


def test_sampling_and_engine_settings_change_identity():
    a = bs.System.from_pretrained("org/model", revision=SHA)
    b = bs.System.from_pretrained("org/model", revision=SHA, generation=bs.GenerationConfig(max_tokens=5))
    c = bs.System.from_pretrained("org/model", revision=SHA, dtype="bfloat16")
    assert len({s.spec.digest for s in (a, b, c)}) == 3


def test_bad_inputs_and_wrong_version_refused_before_engine_load():
    module, calls = fake_vllm()
    with patch.dict(sys.modules, {"vllm": module}), patch("benchstudio.vllm_backend.version", return_value="different"):
        runtime = bs.System.from_pretrained("org/model", revision=SHA).runtime
        with pytest.raises(TypeError, match="string"):
            runtime.generate_batch([{"not": "text"}])
        with pytest.raises(ImportError, match="extra"):
            runtime("x")
        assert calls["loads"] == []
    with pytest.raises(ValueError, match="revision"):
        bs.System.from_pretrained("org/model", revision="main")
    with pytest.raises(ValueError):
        bs.GenerationConfig(temperature=float("nan"))
    with pytest.raises(ValueError):
        bs.System.from_pretrained("org/model", revision=SHA, tensor_parallel_size=True)


def test_backend_alignment_errors_cannot_silently_score_wrong_prompts():
    module, _ = fake_vllm()
    module.LLM.generate = lambda *a, **k: []
    with patch.dict(sys.modules, {"vllm": module}), patch("benchstudio.vllm_backend.version", return_value="0.33.0"), patch("benchstudio.backend_loading.metadata.version", return_value="0.33.0"):
        runtime = bs.System.from_pretrained("org/model", revision=SHA).runtime
        with pytest.raises(ValueError, match="number"):
            runtime.generate_batch(["x"])


def test_batching_is_explicit_and_unavailable_for_plain_callable():
    system = bs.System.from_callable(lambda x: x, name="custom", revision="r1")
    data = bs.Benchmark("t", "r1", [1], [1], lambda a,b: bs.Score(a == b), "r1")
    pipeline = bs.pipeline("system-evaluation", system=system, benchmark=data)
    with pytest.raises(TypeError, match="generate_batch"):
        pipeline(batch_size=1)
    with pytest.raises(ValueError):
        pipeline(batch_size=0)
    assert pipeline().trials[0].success


def test_async_misuse_and_public_config_reassignment_fail_before_loading():
    import asyncio
    module, calls = fake_vllm()
    with patch.dict(sys.modules, {"vllm": module}), patch("benchstudio.vllm_backend.version", return_value="0.33.0"), patch("benchstudio.backend_loading.metadata.version", return_value="0.33.0"):
        system = bs.System.from_pretrained("org/model", revision=SHA)
        with pytest.raises(AttributeError):
            system.runtime.config = bs.VLLMConfig("other/model", SHA)
        with pytest.raises(AttributeError):
            system.runtime.generation = bs.GenerationConfig(max_tokens=1)
        async def check():
            with pytest.raises(RuntimeError, match="event loop"):
                system.runtime("x")
        asyncio.run(check())
        assert calls["loads"] == []


def test_prompt_alignment_refused_even_with_correct_result_count():
    module, _ = fake_vllm()
    module.LLM.generate = lambda *a, **k: [types.SimpleNamespace(
        prompt="wrong", outputs=[types.SimpleNamespace(text="response")])]
    with patch.dict(sys.modules, {"vllm": module}), patch("benchstudio.vllm_backend.version", return_value="0.33.0"), patch("benchstudio.backend_loading.metadata.version", return_value="0.33.0"):
        with pytest.raises(ValueError, match="order"):
            bs.System.from_pretrained("org/model", revision=SHA).runtime("x")
