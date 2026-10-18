import json

from benchstudio.campaigns import load_campaign_document
from benchstudio.cli import main


def test_cli_compiles_campaign_spec(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    plan_path = tmp_path / "plan.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "cli-run"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        ["benchstudio-run", "--campaign-spec", str(spec_path), "--plan-output", str(plan_path)],
    )
    assert main() == 0
    assert json.loads(plan_path.read_text(encoding="utf-8"))["run_id"] == "cli-run"
    assert "compiled_plan=" in capsys.readouterr().out


def test_campaign_document_loader_rejects_non_mapping_json(tmp_path):
    path = tmp_path / "campaign.json"
    path.write_text("[]", encoding="utf-8")
    import pytest

    with pytest.raises(ValueError, match="top-level mapping"):
        load_campaign_document(path)


def test_cli_can_execute_compiled_campaign_with_mock_backend(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    plan_path = tmp_path / "plan.json"
    output = tmp_path / "run"
    archive = tmp_path / "campaign.zip"
    artifact_store = tmp_path / "artifact-store"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "cli-execute"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1],
                    "paired": True,
                    "conditions": [{"denoising_steps": 2, "action_prefix": 1}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--plan-output",
            str(plan_path),
            "--output",
            str(output),
            "--execute-mock",
            "--audit",
            "--archive-output",
            str(archive),
            "--artifact-store",
            str(artifact_store),
        ],
    )
    assert main() == 0
    assert (output / "attempt-results.jsonl").is_file()
    assert archive.is_file()
    assert list(artifact_store.rglob("*.zip"))
    captured = capsys.readouterr()
    assert "campaign_status=completed" in captured.out
    assert "audit_status=qualified" in captured.out
    assert "artifact_sha256=" in captured.out
