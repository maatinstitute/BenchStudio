from types import SimpleNamespace
from unittest.mock import patch

import pytest

import benchstudio as bs


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


def test_robotics_pipeline_compiles_runs_and_returns_artifact_receipt(tmp_path):
    plan = SimpleNamespace(protocol={"M": {"adapter": "fake"}, "S": {"environments": []}})
    summary = bs.CampaignExecutionSummary(
        run_id="quickstart",
        plan_digest_sha256="a" * 64,
        committed_attempt_ids=("attempt-1",),
        failed_attempt_ids=(),
        skipped_attempt_ids=(),
        missing_attempt_ids=(),
        leased_out_attempt_ids=(),
        cancelled_attempt_ids=(),
    )
    pipeline_module = __import__("benchstudio.pipeline", fromlist=["unused"])
    adapters_module = __import__("benchstudio.adapters", fromlist=["unused"])
    models_module = __import__("benchstudio.model_adapters", fromlist=["unused"])
    adapters_module = __import__("benchstudio.adapters", fromlist=["unused"])
    models_module = __import__("benchstudio.model_adapters", fromlist=["unused"])
    adapters_module = __import__("benchstudio.adapters", fromlist=["unused"])
    models_module = __import__("benchstudio.model_adapters", fromlist=["unused"])
    with (
        patch.object(pipeline_module, "compile_campaign_spec", return_value=plan),
        patch.object(adapters_module, "default_registry"),
        patch.object(models_module, "default_model_registry"),
        patch.object(pipeline_module, "CampaignExecutor") as executor_type,
    ):
        executor = executor_type.return_value
        executor.run.return_value = summary
        runner = bs.pipeline(
            "robotics-evaluation",
            campaign=_campaign(),
            output_dir=tmp_path / "run",
            execution="registry",
        )
        result = runner()

    assert isinstance(result, bs.CampaignRun)
    assert result.execution is summary
    assert result.to_dict()["plan_digest_sha256"] == "a" * 64
    assert "1 completed" in result.summary()
    executor_type.assert_called_once()
    executor.run.assert_called_once_with()


def test_robotics_pipeline_keeps_analysis_explicit(tmp_path):
    summary = bs.CampaignExecutionSummary(
        run_id="quickstart",
        plan_digest_sha256="b" * 64,
        committed_attempt_ids=(),
        failed_attempt_ids=(),
        skipped_attempt_ids=(),
        missing_attempt_ids=(),
        leased_out_attempt_ids=(),
        cancelled_attempt_ids=(),
    )
    pipeline_module = __import__("benchstudio.pipeline", fromlist=["unused"])
    with (
        patch.object(pipeline_module, "compile_campaign_spec", return_value=object()),
        patch.object(adapters_module, "default_registry"),
        patch.object(models_module, "default_model_registry"),
        patch.object(pipeline_module, "CampaignExecutor") as executor_type,
        patch.object(pipeline_module, "audit_campaign_directory") as audit,
    ):
        executor_type.return_value.run.return_value = summary
        result = bs.pipeline(
            "robotics-evaluation",
            campaign=_campaign(),
            output_dir=tmp_path / "run",
        )()
        audit.assert_not_called()
        result.analyze(claim_type=bs.ClaimType.PAIRED_COMPARISON)
        audit.assert_called_once_with(
            tmp_path / "run", claim_type=bs.ClaimType.PAIRED_COMPARISON, evidence=None
        )


def test_pipeline_rejects_missing_model_or_environment_adapters(tmp_path):
    pipeline_module = __import__("benchstudio.pipeline", fromlist=["unused"])
    with (
        patch.object(pipeline_module, "compile_campaign_spec") as compile_spec,
        patch.object(adapters_module, "default_registry"),
        patch.object(models_module, "default_model_registry"),
    ):
        compile_spec.return_value = SimpleNamespace(protocol={
            "M": {},
            "S": {"environments": [{"id": "local-sim", "kind": "simulator"}]},
        })
        runner = bs.pipeline(
            "robotics-evaluation",
            campaign=_campaign(),
            output_dir=tmp_path / "run",
        )
        with pytest.raises(ValueError, match="model.adapter"):
            runner.run()


def test_mock_pipeline_requires_explicit_mode(tmp_path):
    with pytest.raises(ValueError, match="execution must be"):
        bs.pipeline(
            "robotics-evaluation",
            campaign=_campaign(),
            output_dir=tmp_path / "run",
            execution="implicit",
        )
