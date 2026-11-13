"""Exercise the public authoring contract from an installed distribution."""

from __future__ import annotations

from importlib.metadata import distribution

from reva import PairedStudy, condition_grid, simulator_environment


def main() -> None:
    metadata = distribution("reva")
    assert metadata.version == "0.1.0"
    assert metadata.metadata["License-Expression"] == "LicenseRef-Research-Use-1.1"

    study = PairedStudy(
        name="installed-package-smoke",
        task_id="task",
        conditions=condition_grid(
            generation_effort=[2, 5],
            actions_before_refresh=[2],
        ),
        seeds=(1,),
        environments=(simulator_environment("simulator"),),
    )
    plan = study.freeze()
    assert len(plan.attempts) == 2
    assert len(plan.plan_digest_sha256) == 64
    assert {attempt.key.environment_id for attempt in plan.attempts} == {"simulator"}


if __name__ == "__main__":
    main()
