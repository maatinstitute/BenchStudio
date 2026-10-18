"""RoboPAD conservative exposure inventory and fail-closed split audit."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

FAMILY = re.compile(
    r"(?:libero_object/task(?:0|[1-9][0-9]*)/demo(?:0|[1-9][0-9]*)|"
    r"libero_spatial/task(?:0|[1-9][0-9]*)/initial(?:0|[1-9][0-9]*))"
)
SPLITS = {"development", "training", "protocol_validation", "final_test"}
LIMITATIONS = [
    "Dataset HDF5 and initial-state-bank bytes/hashes are unresolved.",
    "Task and cross-dataset family aliases are unresolved; numeric IDs are namespace-local.",
    "Broader rejected/attempted teacher-parent coverage is unresolved.",
    "Planned identities are quarantined without claiming completed evaluations.",
    "Schema 1 is a provisional quarantine inventory and cannot certify freshness.",
]


def family_id(value: Any) -> str:
    if not isinstance(value, str) or FAMILY.fullmatch(value) is None:
        raise ValueError(f"Missing or noncanonical parent family identity: {value!r}")
    return value


def demo_family(row: dict[str, Any]) -> str:
    try:
        task, demo = row["task_id"], row["demo_index"]
    except (KeyError, TypeError) as exc:
        raise ValueError("Missing task_id/demo_index") from exc
    if type(task) is not int or type(demo) is not int or min(task, demo) < 0:
        raise ValueError("Task and demonstration indices must be nonnegative integers")
    return family_id(f"libero_object/task{task}/demo{demo}")


def audit_splits(inventory: dict[str, Any], assignments: list[dict[str, Any]]) -> dict[str, Any]:
    """Audit parent overlap only; never promote not-found into fresh data."""
    if inventory.get("schema_version") != 1 or not inventory.get("families"):
        raise ValueError("A nonempty schema-1 quarantine inventory is required")
    quarantine = {family_id(row.get("family_id")) for row in inventory["families"]}
    if not isinstance(assignments, list) or not assignments:
        raise ValueError("Nonempty assignment list required")
    groups: dict[str, set[str]] = {}
    for row in assignments:
        fid = family_id(row.get("family_id"))
        split = row.get("split")
        if split not in SPLITS:
            raise ValueError(f"Unknown or missing split: {split!r}")
        groups.setdefault(fid, set()).add(split)
    overlaps = sorted(fid for fid, splits in groups.items() if len(splits) > 1)
    forbidden = sorted(
        fid
        for fid, splits in groups.items()
        if fid in quarantine and splits & {"protocol_validation", "final_test"}
    )
    return {
        "structurally_disjoint": not overlaps and not forbidden,
        "freshness_certified": False,
        "cross_split_families": overlaps,
        "quarantined_families": forbidden,
        "quarantined_reuse": sorted(set(groups) & quarantine),
        "not_found_in_inspected_sources": sorted(set(groups) - quarantine),
        "unresolved": list(LIMITATIONS),
        "unique_assignment_families": len(groups),
    }


def build_inventory(workspace: Path) -> dict[str, Any]:
    """Read only explicitly scoped retained sources; no recursive outcome search."""
    root = Path(workspace)
    repo = "repos/RoboPAD/"
    sources: list[dict[str, str]] = []
    families: dict[str, dict[str, Any]] = {}

    def read(path: str) -> Any:
        raw = (root / path).read_bytes()
        sources.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    def add(fid: str, source: str, pointer: str, role: str, task_hash: str | None = None) -> None:
        fid = family_id(fid)
        record = families.setdefault(
            fid, {"family_id": fid, "dataset_sha256": None, "evidence": []}
        )
        evidence: dict[str, Any] = {"source": source, "pointer": pointer, "role": role}
        if task_hash is not None:
            if not isinstance(task_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", task_hash):
                raise ValueError("Invalid retained task hash")
            evidence["reported_bddl_sha256"] = task_hash
        if evidence not in record["evidence"]:
            record["evidence"].append(evidence)

    pilot = "robopad-paired-pilot/artifacts/scaled-3tasks-8parents/inventory.json"
    for index, row in enumerate(read(pilot)["expected_cells"]):
        parts = row["task_id"].split("/")
        if len(parts) != 3 or parts[0] != "libero_object":
            raise ValueError("Unexpected pilot task identity")
        demo = re.fullmatch(r"demo_([0-9]+)", row["demo_id"])
        if demo is None:
            raise ValueError("Unexpected pilot demo identity")
        fid = demo_family({"task_id": int(parts[1]), "demo_index": int(demo[1])})
        add(fid, pilot, f"/expected_cells/{index}", "pilot_planned")

    entries = [
        (
            "robopad-paired-pilot/docs/replication-20260913/protocol.json",
            ["parents"],
            "replication_reserved",
        ),
        (
            "pi05-correction-feasibility-20260913/matched-collection-v1/selection_manifest.json",
            ["parents"],
            "matched_collection_selected",
        ),
        (
            "pi05-training-readiness-20260913/analysis/snapshot/fresh-sources-01/preparation_summary.json",
            ["planned_parents"],
            "earlier_preparation_planned",
        ),
        (
            "pi05-correction-feasibility-20260913/mixed-training-v1/analysis/final-audit-01/result.json",
            ["preparation_summary", "planned_parents"],
            "matched_evaluation_planned",
        ),
    ]
    for path, keys, role in entries:
        rows = read(path)
        for key in keys:
            rows = rows[key]
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"Missing parent rows in {path}")
        for index, row in enumerate(rows):
            add(demo_family(row), path, "/" + "/".join(keys) + f"/{index}", role)

    path = repo + "experiments/gen_protocol.py"
    raw = (root / path).read_bytes()
    sources.append({"path": path, "sha256": hashlib.sha256(raw).hexdigest()})
    declarations = [
        node
        for node in ast.parse(raw).body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "DEVELOPMENT" for target in node.targets
        )
    ]
    if len(declarations) != 1:
        raise ValueError("Development constant unresolved")
    add(ast.literal_eval(declarations[0].value), path, "DEVELOPMENT", "development")

    for suffix, key, role in [
        (
            "generalization-2026-09-11/results/generalization_validation_001/manifest.json",
            "episodes",
            "old_validation",
        ),
        (
            "generalization-2026-09-11/results/generalization_validation_002/manifest.json",
            "episodes",
            "old_validation",
        ),
        ("heldout-2026-09-12/training/dataset_manifest.json", "samples", "accepted_training"),
        ("heldout-2026-09-12/training/test_manifest.json", "episodes", "old_test_reserved"),
    ]:
        path = repo + "artifacts/evidence/" + suffix
        rows = read(path)[key]
        seen: set[str] = set()
        for index, row in enumerate(rows):
            fid = family_id(row["episode_id"])
            task = row.get("task_id", row.get("task"))
            expected = f"{row['suite']}/task{task}/initial{row['initial_state']}"
            if fid != expected or row["suite"] != "libero_spatial":
                raise ValueError("Conflicting SmolVLA identity fields")
            if fid not in seen:
                add(fid, path, f"/{key}/{index}", role, row.get("bddl_sha256"))
                seen.add(fid)
    records = [families[key] for key in sorted(families)]
    return {
        "schema_version": 1,
        "status": "provisional_quarantine_only",
        "freshness_certified": False,
        "unresolved": LIMITATIONS,
        "descendant_rule": (
            "All seeds, anchors, interventions and teacher attempts inherit parent family_id."
        ),
        "sources": sources,
        "families": records,
        "counts": {
            suite: sum(record["family_id"].startswith(suite + "/") for record in records)
            for suite in ("libero_object", "libero_spatial")
        },
    }
