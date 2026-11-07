import benchstudio as bs
from benchstudio.pipeline import _campaign_from_direct_inputs


def test_transformers_style_inputs_compile_without_executing_runtime():
    spec = _campaign_from_direct_inputs(
        task={"id": "libero/spatial/task-0", "revision": "dataset-revision-1"},
        task_revision=None,
        model={
            "adapter": "smolvla",
            "checkpoint": "sha256:" + "b" * 64,
            "config": {"command": ["python", "policy.py"]},
        },
        environment={
            "adapter": "external_command",
            "id": "libero-local",
            "config": {"command": ["python", "environment.py"]},
        },
        seeds=[7, 8],
        conditions=[{"id": "baseline", "denoising_steps": 10}],
        run_id="smolvla-libero-baseline",
        benchmark="libero",
    )

    plan = bs.compile_campaign_spec(spec)

    assert len(plan.attempts) == 2
    assert plan.protocol["M"]["checkpoint"] == "sha256:" + "b" * 64
    assert plan.protocol["S"]["environments"][0]["adapter"] == "external_command"
