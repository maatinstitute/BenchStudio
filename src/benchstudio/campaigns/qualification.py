"""Launch authorization for a frozen Refinement/Refresh v3 confirmation plan."""

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .frozen_plan import FrozenCampaignPlan


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _read(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        document = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load qualification file {path.name}") from exc
    if not isinstance(document, dict):
        raise ValueError(f"qualification file {path.name} must be a JSON object")
    return document, hashlib.sha256(raw).hexdigest()


def verify_refinement_qualification(
    plan: FrozenCampaignPlan, directory: Path | None, trusted_approval_sha256: str | None
) -> str | None:
    """Return the qualified model. The approver supplies the digest out of band."""
    protocol = plan.protocol or {}
    experiment = (protocol.get("P") or {}).get("experiment") or {}
    if "refinement_v3" not in experiment:
        if directory is not None or trusted_approval_sha256 is not None:
            raise ValueError("qualification options require a frozen refinement_v3 declaration")
        return None

    FrozenCampaignPlan.from_dict(plan.to_dict())
    declaration = experiment["refinement_v3"]
    if not isinstance(declaration, dict):
        raise ValueError("refinement_v3 must be a JSON object")
    model = declaration.get("model")
    if model not in ("pi0.5", "smolvla") or declaration.get("stage") != "confirmation":
        raise ValueError("refinement_v3 requires a supported confirmation model")
    runtime = declaration.get("runtime")
    required = {"runner", "checkpoint", "simulator_stack", "renderer", "assets", "normalization"}
    if (
        not isinstance(runtime, dict)
        or not required.issubset(runtime)
        or not all(_sha(value) for value in runtime.values())
    ):
        raise ValueError("refinement_v3 requires pinned SHA-256 runtime identities")
    if directory is None or not _sha(trusted_approval_sha256):
        raise ValueError("refinement_v3 requires a qualification directory and trusted approval digest")

    approval, digest = _read(directory / "approval.json")
    if (
        digest != trusted_approval_sha256
        or approval.get("schema") != "benchstudio.refinement_v3_approval.v1"
        or approval.get("plan_digest_sha256") != plan.plan_digest_sha256
    ):
        raise ValueError("qualification approval does not match the trusted digest and frozen plan")

    observed, _ = _read(directory / "runtime.json")
    if observed != runtime:
        raise ValueError("observed runtime identities differ from the frozen plan")
    names = {"engineering_preflight", "evaluator"}
    if model == "pi0.5":
        names.update({"stock_parity", "g02"})
    evidence = approval.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != names:
        raise ValueError("qualification approval does not bind every required report")
    for name in sorted(names):
        report, report_digest = _read(directory / f"{name}.json")
        if evidence[name] != report_digest or report.get("passed") is not True:
            raise ValueError(f"qualification report {name} is changed or has not passed")
    return model
