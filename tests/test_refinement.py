import json
import subprocess
from unittest.mock import patch
import pytest
import benchstudio as bs
from benchstudio.refinement import RefinementWorkspace, RefinementPreparation


def test_public_workspace_preserves_arguments_and_never_runs_suggestions(tmp_path):
    repo = tmp_path / 'paper checkout'
    script = repo / 'experiments/tooling/cross_policy_v3/prepare_campaign.py'
    script.parent.mkdir(parents=True)
    script.write_text('')
    report = {'schema': 'refinement_campaign_preparation_v1', 'model': 'pi05', 'read_only': True,
              'issues': [], 'execution_authorized': False, 'commands': {'later': ['never-execute']}}
    with patch('benchstudio.refinement.subprocess.run', return_value=subprocess.CompletedProcess(
            [], 0, json.dumps(report), '')) as run:
        result = RefinementWorkspace(repo, tmp_path / 'workspace', python='/native/python').prepare(model='pi05')
    assert run.call_count == 1
    assert run.call_args.args[0] == ['/native/python', str(script), '--workspace',
                                    str(tmp_path / 'workspace'), '--model', 'pi05']
    assert result.commands('pi05') == {'later': ['never-execute']}
    assert 'release pending' in result.summary()


def test_missing_helper_and_invalid_models_fail_before_subprocess(tmp_path):
    with patch('benchstudio.refinement.subprocess.run') as run:
        with pytest.raises(FileNotFoundError, match='preparation helper'):
            RefinementWorkspace(tmp_path, tmp_path).prepare()
        with pytest.raises(ValueError, match='model'):
            RefinementWorkspace(tmp_path, tmp_path).prepare(model='other')
    run.assert_not_called()
