from types import SimpleNamespace
from unittest.mock import patch

import pytest

import benchstudio as bs
from benchstudio.analysis.claims import ClaimType
from benchstudio.campaigns.executor import CampaignExecutionSummary
from benchstudio.pipeline import CampaignRun


def _campaign():
    return {
        "schema": "benchstudio.campaign.v1",
        "experiment": {"name": "quickstart"},
        "model": {"adapter": "fake-policy"},
        "task": {"task_id": "pick-cube"},
        "environments": [
            {"id": "local-sim", "kind": "simulator", "adapter": "fake-sim"}
        ],
        "evaluation": {
            "seeds": [1],
            "conditions": [{"id": "baseline"}],
            "paired": True,
        },
    }


def _plan():
    return SimpleNamespace(protocol={"M": {"adapter": "fake"}, "S": {"environments": []}})


def _summary():
    return CampaignExecutionSummary(
        run_id="quickstart",
        plan_digest_sha256="a" * 64,
        committed_attempt_ids=("attempt-1",),
        failed_attempt_ids=(),
        skipped_attempt_ids=(),
        missing_attempt_ids=(),
        leased_out_attempt_ids=(),
        cancelled_attempt_ids=(),
    )


def _modules():
    return (
        __import__("benchstudio.pipeline", fromlist=["unused"]),
        __import__("benchstudio.adapters", fromlist=["unused"]),
        __import__("benchstudio.model_adapters", fromlist=["unused"]),
    )


def _patched_executor():
    from contextlib import ExitStack

    stack = ExitStack()
    pipeline_module, adapters_module, models_module = _modules()
    stack.enter_context(patch.object(adapters_module, "default_registry"))
    stack.enter_context(patch.object(models_module, "default_model_registry"))
    executor_type = stack.enter_context(patch.object(pipeline_module, "CampaignExecutor"))
    executor_type.return_value.run.return_value = _summary()
    return stack, pipeline_module, executor_type


def test_robotics_pipeline_compiles_runs_and_returns_artifact_receipt(tmp_path):
    stack, pipeline_module, executor_type = _patched_executor()
    with stack:
        with patch.object(pipeline_module, "compile_campaign_spec", return_value=_plan()):
            runner = bs.pipeline(
                "robotics-evaluation",
                campaign=_campaign(),
                output_dir=tmp_path / "run",
                execution="registry",
            )
            result = runner()

    assert isinstance(result, CampaignRun)
    assert result.execution.committed_attempt_ids == ("attempt-1",)
    assert result.to_dict()["plan_digest_sha256"] == "a" * 64
    assert "1 completed" in result.summary()
    executor_type.assert_called_once()
    executor_type.return_value.run.assert_called_once_with()


def test_direct_transformers_style_inputs_compile_to_frozen_campaign(tmp_path):
    stack, pipeline_module, _ = _patched_executor()
    with stack:
        compiled = {}

        def compile_spec(value):
            compiled.update(value)
            return _plan()

        with patch.object(pipeline_module, "compile_campaign_spec", side_effect=compile_spec):
            result = bs.pipeline(
                "robotics-evaluation",
                task={"id": "libero/spatial/task-0", "revision": "dataset-sha256"},
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
                run_id="smolvla-libero-smoke",
                benchmark="libero",
                output_dir=tmp_path / "run",
            )()

    assert compiled["model"]["adapter"] == "smolvla"
    assert compiled["model"]["checkpoint"] == "sha256:" + "b" * 64
    assert compiled["task"] == {
        "task_id": "libero/spatial/task-0",
        "task_revision": "dataset-sha256",
        "benchmark": "libero",
    }
    assert compiled["environments"][0]["adapter"] == "external_command"
    assert compiled["evaluation"]["seeds"] == [7, 8]
    assert compiled["evaluation"]["paired"] is True
    assert isinstance(result, CampaignRun)


def test_robotics_pipeline_keeps_analysis_explicit(tmp_path):
    stack, pipeline_module, _ = _patched_executor()
    with stack:
        with (
            patch.object(pipeline_module, "compile_campaign_spec", return_value=_plan()),
            patch.object(pipeline_module, "audit_campaign_directory") as audit,
        ):
            result = bs.pipeline(
                "robotics-evaluation",
                campaign=_campaign(),
                output_dir=tmp_path / "run",
            )()
            audit.assert_not_called()
            result.analyze(claim_type=ClaimType.PAIRED_COMPARISON)
            audit.assert_called_once_with(
                tmp_path / "run", claim_type=ClaimType.PAIRED_COMPARISON, evidence=None
            )


def test_direct_inputs_require_task_revision(tmp_path):
    with pytest.raises(ValueError, match="task_revision is required"):
        bs.pipeline(
            "robotics-evaluation",
            task="libero/task-0",
            model="smolvla",
            environment="external_command",
            seeds=[7],
            conditions=[{"id": "baseline"}],
            run_id="smoke",
            output_dir=tmp_path / "run",
        )()


def test_pipeline_rejects_implicit_execution_mode(tmp_path):
    with pytest.raises(ValueError, match="execution must be"):
        bs.pipeline(
            "robotics-evaluation",
            campaign=_campaign(),
            output_dir=tmp_path / "run",
            execution="implicit",
        )
