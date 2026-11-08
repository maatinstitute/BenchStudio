"""Optional Refinement vs Refresh operator workflow; no native dependency imports."""
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Mapping


@dataclass(frozen=True)
class RefinementPreparation:
    models: Mapping[str, dict]

    def summary(self) -> str:
        lines = []
        for model, report in self.models.items():
            lines.append(f"{model}: {len(report['issues'])} preparation issue(s); "
                         f"release {'validated' if report['execution_authorized'] else 'pending'}")
            for issue in report['issues']:
                lines.append(f"  {issue['message']} -> {issue['next_action']}")
        return "\n".join(lines)

    def commands(self, model: str) -> dict[str, list[str]]:
        """Argument arrays for explicit operator use. Never executes them."""
        return {name: list(args) for name, args in self.models[model]['commands'].items()}


@dataclass(frozen=True)
class RefinementWorkspace:
    """Prepare the pinned native paper checkout through its offline helper.

    repository must be a trusted, reviewed checkout. python is its stdlib-capable
    interpreter, which can be Python 3.8 independently of BenchStudio's runtime.
    prepare() invokes only prepare_campaign.py; it never invokes returned commands.
    """
    repository: str | Path
    workspace: str | Path | None = None
    python: str = sys.executable

    def prepare(self, *, model: str | None = None) -> RefinementPreparation:
        models = (model,) if model is not None else ('smolvla', 'pi05')
        if any(name not in ('smolvla', 'pi05') for name in models):
            raise ValueError('model must be smolvla or pi05')
        repo = Path(self.repository).resolve()
        script = repo / 'experiments/tooling/cross_policy_v3/prepare_campaign.py'
        if not script.is_file():
            raise FileNotFoundError(f'Integrate the paper preparation helper first: {script}')
        workspace = (repo / "experiments/runs/cross_policy_confirmation_v2"
                     if self.workspace is None else Path(self.workspace).resolve())
        reports = {}
        for name in models:
            command = [str(self.python), str(script), '--workspace',
                       str(workspace), '--model', name]
            result = subprocess.run(command, cwd=repo, capture_output=True, text=True,
                                    timeout=60, check=False)
            if result.returncode:
                raise RuntimeError(f'{name} preparation failed ({result.returncode}): {result.stderr.strip()}')
            try:
                report = json.loads(result.stdout)
                if (report['schema'] != 'refinement_campaign_preparation_v1'
                        or report['model'] != name or report['read_only'] is not True
                        or type(report['issues']) is not list
                        or type(report['execution_authorized']) is not bool
                        or type(report['commands']) is not dict):
                    raise ValueError('unexpected report schema')
                for args in report['commands'].values():
                    if not isinstance(args, list) or not args or any(type(a) is not str for a in args):
                        raise ValueError('invalid command argument array')
            except (ValueError, KeyError, TypeError) as error:
                raise ValueError(f'{name}: invalid preparation report: {error}') from error
            reports[name] = report
        return RefinementPreparation(reports)
