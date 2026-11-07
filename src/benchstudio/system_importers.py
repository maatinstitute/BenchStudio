"""Strict read-only import of Inspect Robots EvalLog v3 snapshots.

The importer does not import Inspect Robots itself, invoke robot control,
transform source grades, or guess unavailable pairing identity fields.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Mapping

from .system_evidence import SystemRun, Trial, TrialKey
from .system_spec import SystemSpec


def import_inspect_robots(
    path: str | Path,
    *,
    system: SystemSpec,
    task_revision: str,
    protocol_digest: str,
    evaluator_revision: str,
    environment_revision: str,
    seed_by_scene: Mapping[str, int],
    condition: str,
    score_key: str,
    trust_grader: bool = False,
) -> SystemRun:
    """Import a version-3 log with explicit metadata needed for pairing.

    A scorer may report continuous [0, 1] progress: only EXACT 0 or 1
    values are promoted to binary success when caller explicitly chooses
    score_key. Qualification is the caller's responsibility.
    """
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("source must be a regular non-symlink file")
    data = path.read_bytes()
    log = json.loads(data)
    if not isinstance(log, dict) or log.get("version") != 3:
        raise ValueError("only Inspect Robots EvalLog version 3 is supported")
    eval_spec = log.get("eval")
    if not isinstance(eval_spec, dict):
        raise ValueError("EvalLog missing eval spec")
    task = eval_spec.get("task")
    grader = eval_spec.get("grader")
    if not isinstance(task, str) or not task:
        raise ValueError("EvalLog must declare task")
    if not isinstance(grader, str) or not grader:
        raise ValueError("EvalLog has no declared grader; refuse inferred scoring")
    if not score_key or not isinstance(score_key, str):
        raise ValueError("explicit score_key required")
    if not isinstance(trust_grader, bool):
        raise ValueError("trust_grader must be boolean")
    if not isinstance(seed_by_scene, Mapping):
        raise ValueError("seed_by_scene mapping required")
    native_env_rev = eval_spec.get("environment_revision")
    if native_env_rev and native_env_rev != environment_revision:
        raise ValueError("declared environment revision conflicts with source log")
    samples = log.get("samples")
    if not isinstance(samples, list):
        raise ValueError("EvalLog samples missing")
    rows = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("invalid scene result")
        scene_id = sample.get("scene_id")
        if not isinstance(scene_id, str) or scene_id not in seed_by_scene:
            raise ValueError("no verified scene-to-seed identity")
        seed = seed_by_scene[scene_id]
        epochs = sample.get("epochs")
        if not isinstance(epochs, list) or not epochs:
            raise ValueError("missing raw per-trial epochs; do not infer sample count")
        status = sample.get("status")
        if status not in {"success", "error", "cancelled"}:
            raise ValueError("invalid Inspect Robots scene execution status")
        record_ids = sample.get("record_ids", [])
        if record_ids and (not isinstance(record_ids, list) or len(record_ids) != len(epochs)):
            raise ValueError("record_ids do not match per-trial epochs")
        for repetition, scores in enumerate(epochs):
            if not isinstance(scores, dict):
                raise ValueError("epoch scores must be mappings")
            reported = scores.get(score_key)
            if reported is not None and (
                type(reported) not in (float, int) or not math.isfinite(reported)
            ):
                raise ValueError("score must be a finite numeric value")
            metrics = {
                name: float(value) for name, value in scores.items()
                if type(value) in (float, int) and math.isfinite(value)
            }
            trial_status = (
                "cancelled" if status == "cancelled"
                else "execution_failed" if status == "error" or not scores
                else "completed"
            )
            binary = (
                bool(reported) if trial_status == "completed" and reported in (0, 1)
                else None
            )
            source_id = record_ids[repetition] if record_ids else None
            if source_id is not None and (not isinstance(source_id, str) or not source_id):
                raise ValueError("invalid source record ID")
            trial_id = source_id or f"{scene_id}:epoch-{repetition}"
            rows.append(Trial(
                trial_id=trial_id,
                key=TrialKey(
                    task, task_revision, scene_id, condition, seed,
                    repetition, environment_revision, protocol_digest,
                    grader, evaluator_revision,
                ),
                system_digest=system.digest, status=trial_status,
                success=binary,
                outcome_source="declared" if trust_grader else "supplementary",
                authoritative=trust_grader,
                metrics=metrics,
            ))
    return SystemRun(
        run_id=f"inspect-robots:{hashlib.sha256(data).hexdigest()[:16]}",
        system=system, trials=tuple(rows),
        source_digests={"inspect_robots_eval_log": hashlib.sha256(data).hexdigest()},
    )
