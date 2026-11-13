"""Run the deterministic mock counterfactual checkpoint.

This is a protocol/evidence example only. It does not simulate robot physics,
disturbances, safety, or official benchmark scoring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from reva.campaigns import (
    CounterfactualEvaluation,
    Intervention,
    compile_campaign_spec,
    compile_counterfactual_plan,
    execute_counterfactual_plan,
)


def main() -> int:
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--campaign-spec",
        type=Path,
        default=root / "campaigns/mock-robustness.json",
    )
    parser.add_argument(
        "--interventions",
        type=Path,
        default=root / "campaigns/mock-robustness-interventions.json",
    )
    parser.add_argument("--output", type=Path, default=Path("runs/mock-robustness"))
    args = parser.parse_args()

    plan = compile_campaign_spec(json.loads(args.campaign_spec.read_text(encoding="utf-8")))
    raw_interventions = json.loads(args.interventions.read_text(encoding="utf-8"))
    interventions = tuple(
        Intervention(
            value["intervention_id"],
            value["transition_index"],
            value["kind"],
            value.get("parameters", {}),
        )
        for value in raw_interventions
    )
    counterfactual = compile_counterfactual_plan(plan, interventions)
    counterfactual_path = args.output / "counterfactual-plan.json"
    counterfactual_path.parent.mkdir(parents=True, exist_ok=True)
    counterfactual.write(counterfactual_path)

    def evaluate(cell):
        if cell.branch == "nominal":
            return CounterfactualEvaluation(
                success=True,
                metadata={"authority": "mock", "physics": False},
            )
        intervention = cell.intervention
        parameters = intervention.parameters
        return CounterfactualEvaluation(
            success=False,
            recovery_time_ms=parameters.get("recovery_time_ms"),
            failure_category=parameters.get("failure_category", "mock_intervention"),
            metadata={"authority": "mock", "physics": False},
        )

    results = execute_counterfactual_plan(counterfactual, evaluate, output=args.output)
    print(
        json.dumps(
            {
                "status": "completed",
                "physics": "external",
                "pairs": len(counterfactual.pairs),
                "branches": len(results),
                "plan": str(counterfactual_path),
                "results": str(args.output / "counterfactual-results.jsonl"),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
