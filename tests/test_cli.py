import json

from benchstudio.campaigns import LocalArtifactStore, load_campaign_document
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


def test_cli_reports_adapter_readiness(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--readiness"])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert {item["simulator_id"] for item in report["simulators"]} >= {"mock", "mujoco"}
    assert {item["adapter_id"] for item in report["models"]} >= {"mock"}


def test_cli_verifies_existing_artifact_without_execution(monkeypatch, tmp_path, capsys):
    from benchstudio.evidence import sha256_file
    from benchstudio.mock import MockPolicy, MockSimulator
    from benchstudio.runner import RunConfig, run_episodes

    run_dir = tmp_path / "run"
    run_episodes(MockPolicy(), MockSimulator(), RunConfig(), run_dir)
    digest = sha256_file(run_dir / "artifact-manifest.json")
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--verify-artifact",
            str(run_dir),
            "--trusted-manifest-sha256",
            digest,
        ],
    )
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is True
    assert result["trust_anchor"]["external_reference_supplied"] is True


def test_cli_returns_nonzero_for_invalid_artifact(monkeypatch, tmp_path, capsys):
    run_dir = tmp_path / "missing"
    monkeypatch.setattr("sys.argv", ["benchstudio-run", "--verify-artifact", str(run_dir)])
    assert main() == 2
    result = json.loads(capsys.readouterr().out)
    assert result["valid"] is False


def test_cli_executes_declared_registry_adapters(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "registry-campaign.json"
    output = tmp_path / "run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "registry-cli"},
                "model": {"adapter": "mock"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator", "adapter": "mock"}],
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
            "--output",
            str(output),
            "--execute-registry",
        ],
    )
    assert main() == 0
    assert (output / "attempt-results.jsonl").is_file()
    assert "campaign_status=completed" in capsys.readouterr().out


def test_cli_executes_a_frozen_campaign_with_multiple_workers(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "parallel-campaign.json"
    output = tmp_path / "parallel-run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "parallel-cli"},
                "task": {"task_id": "task"},
                "environments": [{"id": "sim", "kind": "simulator"}],
                "evaluation": {
                    "seeds": [1, 2, 3, 4],
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
            "--output",
            str(output),
            "--execute-mock",
            "--workers",
            "2",
        ],
    )
    assert main() == 0
    assert len((output / "attempt-results.jsonl").read_text().splitlines()) == 4
    assert "missing=0" in capsys.readouterr().out


def test_cli_rejects_non_positive_worker_count(monkeypatch, tmp_path):
    spec_path = tmp_path / "campaign.json"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "invalid-workers"},
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
        ["benchstudio-run", "--campaign-spec", str(spec_path), "--workers", "0"],
    )
    with __import__("pytest").raises(SystemExit):
        main()


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


def test_cli_can_select_http_artifact_publication(monkeypatch, tmp_path, capsys):
    spec_path = tmp_path / "campaign.json"
    output = tmp_path / "run"
    spec_path.write_text(
        json.dumps(
            {
                "schema": "benchstudio.campaign.v1",
                "experiment": {"name": "http-artifact"},
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
    seen = {}

    class FakeHttpStore:
        def __init__(self, url):
            seen["url"] = url
            self._local = LocalArtifactStore(tmp_path / "http-store")

        def publish_archive(self, archive, *, digest_sha256):
            return self._local.publish_archive(archive, digest_sha256=digest_sha256)

    monkeypatch.setattr("benchstudio.cli.HttpArtifactStore", FakeHttpStore)
    monkeypatch.setattr(
        "sys.argv",
        [
            "benchstudio-run",
            "--campaign-spec",
            str(spec_path),
            "--output",
            str(output),
            "--execute-mock",
            "--artifact-url",
            "https://objects.example.test/benchstudio",
        ],
    )
    assert main() == 0
    assert seen["url"] == "https://objects.example.test/benchstudio"
    assert "artifact_uri=" in capsys.readouterr().out
