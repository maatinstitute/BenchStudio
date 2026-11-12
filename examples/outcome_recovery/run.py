"""Outcome-recovery reference application built on BenchStudio's campaign API.

Planning needs only BenchStudio. Native execution requires a caller-owned, pinned
simulator/policy evaluator; the example does not approximate task success.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import re
from pathlib import Path
from typing import Any, Callable

from benchstudio.campaigns import (
    CounterfactualEvaluation,
    Intervention,
    compile_campaign_spec,
    compile_counterfactual_plan,
    execute_counterfactual_plan,
    load_frozen_campaign_plan,
)

HERE = Path(__file__).resolve().parent
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_PAIR_HASHES = (
    "initial_state_sha256",
    "fork_state_sha256",
    "prefix_actions_sha256",
    "checkpoint_sha256",
)
_PAIR_STRINGS = ("simulator_revision", "native_success_source")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_interventions(path: Path) -> tuple[Intervention, ...]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 1:
        raise ValueError(
            "the reference application requires exactly one intervention per paired attempt"
        )
    item = data[0]
    if not isinstance(item, dict) or set(item) != {
        "intervention_id", "transition_index", "kind", "parameters"
    }:
        raise ValueError("intervention must declare id, index, kind, and parameters")
    if (
        not isinstance(item["intervention_id"], str)
        or not item["intervention_id"]
        or item["intervention_id"] == "none"
        or not isinstance(item["kind"], str)
        or not item["kind"]
        or type(item["transition_index"]) is not int
        or item["transition_index"] < 0
        or not isinstance(item["parameters"], dict)
    ):
        raise ValueError("invalid intervention identity or parameters")
    return (Intervention(**item),)


def load_evaluator(identifier: str) -> tuple[Callable[[Any], CounterfactualEvaluation], str]:
    module, separator, attribute = identifier.partition(":")
    if not separator or not module or not attribute.isidentifier():
        raise ValueError("--evaluator must use an importable module:function name")
    function = getattr(importlib.import_module(module), attribute)
    if not callable(function):
        raise ValueError("--evaluator target must be callable")
    filename = inspect.getsourcefile(function)
    if not filename or not Path(filename).is_file():
        raise ValueError("evaluator source must exist so it can be recorded by SHA-256")
    return function, _digest(Path(filename))


def bind_evaluator(
    callback: Callable[..., CounterfactualEvaluation], nominal: Any
) -> Callable[[Any], CounterfactualEvaluation]:
    """Supply the frozen attempt identity to an external native evaluator."""
    attempts = {attempt.key.attempt_id: attempt for attempt in nominal.attempts}

    def evaluate(cell: Any) -> CounterfactualEvaluation:
        return callback(
            cell,
            attempt=attempts[cell.nominal_attempt_id],
            protocol=nominal.protocol,
        )

    return evaluate


def assess_pairs(plan: Any, results: Any) -> dict[str, Any]:
    """Check branch identity and metadata agreement; not independent native replay."""
    issues: list[str] = []
    pairs = plan.pairs
    expected = [cell for pair in pairs for cell in (pair.nominal, pair.intervention)]
    if len(results) != len(expected):
        issues.append("missing_or_extra_branches")
    for index, (cell, result) in enumerate(zip(expected, results)):
        if (
            cell.branch_attempt_id != result.branch_attempt_id
            or cell.pair_id != result.pair_id
            or cell.branch != result.branch
            or cell.intervention.intervention_id != result.intervention_id
            or cell.intervention.transition_index != result.transition_index
        ):
            issues.append(f"branch_{index}:identity_mismatch")
    complete_pairs = 0
    paired_wins = 0
    paired_losses = 0
    for index, pair in enumerate(pairs):
        offset = 2 * index
        if len(results) < offset + 2:
            continue
        left, right = results[offset], results[offset + 1]
        prefix = f"pair_{index}"
        if type(left.success) is not bool or type(right.success) is not bool:
            issues.append(f"{prefix}:unknown_outcome")
            continue
        if not isinstance(left.metadata, dict) or not isinstance(right.metadata, dict):
            issues.append(f"{prefix}:missing_provenance")
            continue
        for field in _PAIR_HASHES:
            left_value = left.metadata.get(field)
            right_value = right.metadata.get(field)
            if (
                not isinstance(left_value, str)
                or _SHA256.fullmatch(left_value) is None
                or left_value != right_value
            ):
                issues.append(f"{prefix}:{field}_unverified")
        for field in _PAIR_STRINGS:
            left_value = left.metadata.get(field)
            if (
                not isinstance(left_value, str)
                or not left_value
                or left_value != right.metadata.get(field)
            ):
                issues.append(f"{prefix}:{field}_mismatch")
        if left.metadata.get("intervention_applied") is not False:
            issues.append(f"{prefix}:nominal_disturbed")
        if right.metadata.get("intervention_applied") is not True:
            issues.append(f"{prefix}:intervention_unconfirmed")
        if right.metadata.get("intervention_id") != pair.intervention.intervention.intervention_id:
            issues.append(f"{prefix}:intervention_identity_unconfirmed")
        if not any(issue.startswith(f"{prefix}:") for issue in issues):
            complete_pairs += 1
            paired_wins += int(not left.success and right.success)
            paired_losses += int(left.success and not right.success)
    valid = not issues and complete_pairs == len(pairs)
    return {
        "schema": "benchstudio.outcome_recovery_contract.v1",
        "contract_valid": valid,
        "scope": "paired_record_metadata_only_native_execution_not_independently_verified",
        "planned_pairs": len(pairs),
        "contract_complete_pairs": complete_pairs,
        "intervention_wins": paired_wins if valid else None,
        "intervention_losses": paired_losses if valid else None,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--campaign-spec", type=Path, default=None)
    source.add_argument("--frozen-plan", type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument(
        "--plan-only", action="store_true",
        help="Freeze the paired design; no physics or outcomes",
    )
    action.add_argument(
        "--evaluator", help="Trusted module:function implementing native paired branches"
    )
    parser.add_argument("--interventions", type=Path, default=HERE / "interventions.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.output.is_symlink() or (
        args.output.exists() and (
            not args.output.is_dir() or any(args.output.iterdir())
        )
    ):
        parser.error("refusing to overwrite an existing evidence directory")
    try:
        interventions = load_interventions(args.interventions)
        if args.frozen_plan is not None:
            source_path = args.frozen_plan
            nominal = load_frozen_campaign_plan(source_path)
        else:
            source_path = args.campaign_spec or HERE / "campaign.json"
            nominal = compile_campaign_spec(json.loads(source_path.read_text(encoding="utf-8")))
        evaluator = None
        evaluator_sha = None
        if args.evaluator is not None:
            evaluator, evaluator_sha = load_evaluator(args.evaluator)
        counterfactual = compile_counterfactual_plan(nominal, interventions)
    except (OSError, ValueError, KeyError, TypeError, ImportError, AttributeError) as exc:
        parser.error(str(exc))

    args.output.mkdir(parents=True, exist_ok=True)
    nominal.write(args.output / "campaign-plan.json")
    counterfactual.write(args.output / "counterfactual-plan.json")
    provenance = {
        "schema": "benchstudio.outcome_recovery_example.v1",
        "mode": "plan_only" if evaluator is None else "external_native_evaluator",
        "campaign_plan_sha256": nominal.plan_digest_sha256,
        "counterfactual_plan_sha256": counterfactual.plan_digest_sha256,
        "source_sha256": _digest(source_path),
        "interventions_sha256": _digest(args.interventions),
        "evaluator_sha256": evaluator_sha,
        "native_outcomes_independently_verified": False,
    }
    (args.output / "provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if evaluator is None:
        print(json.dumps({"status": "planned_not_executed", "pairs": len(counterfactual.pairs)}))
        return 0

    try:
        results = execute_counterfactual_plan(
            counterfactual, bind_evaluator(evaluator, nominal), output=args.output
        )
        report = assess_pairs(counterfactual, results)
    except Exception as exc:
        report = {
            "schema": "benchstudio.outcome_recovery_contract.v1",
            "contract_valid": False,
            "issues": [f"evaluation_failed:{type(exc).__name__}:{exc}"],
            "scope": "no_scientific_outcome_claim",
        }
    (args.output / "qualification.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": "contract_complete" if report["contract_valid"] else "unqualified",
                      "report": str(args.output / "qualification.json")}, sort_keys=True))
    return 0 if report["contract_valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
