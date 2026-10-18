from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ScenarioPack:
    scenario_id: str
    task_revision: str
    asset_digests_sha256: tuple[str, ...]
    initial_condition_digest_sha256: str
    success_criterion_version: str
    pack_digest_sha256: str

    @classmethod
    def create(
        cls,
        *,
        scenario_id: str,
        task_revision: str,
        asset_digests_sha256: list[str],
        initial_condition_digest_sha256: str,
        success_criterion_version: str,
    ) -> "ScenarioPack":
        payload = {
            "scenario_id": scenario_id,
            "task_revision": task_revision,
            "asset_digests_sha256": sorted(asset_digests_sha256),
            "initial_condition_digest_sha256": initial_condition_digest_sha256,
            "success_criterion_version": success_criterion_version,
        }
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return cls(
            scenario_id,
            task_revision,
            tuple(payload["asset_digests_sha256"]),
            initial_condition_digest_sha256,
            success_criterion_version,
            digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def load_scenario_pack(path: Path) -> ScenarioPack:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["asset_digests_sha256"] = tuple(data.get("asset_digests_sha256", ()))
    pack = ScenarioPack(**data)
    issues = validate_scenario_pack(pack)
    if issues:
        raise ValueError("invalid scenario pack: " + "; ".join(issues))
    return pack


def validate_scenario_pack(pack: ScenarioPack) -> list[str]:
    issues: list[str] = []
    if not pack.scenario_id or not pack.task_revision:
        issues.append("scenario_id and task_revision are required")
    if not pack.asset_digests_sha256:
        issues.append("at least one asset digest is required")
    if any(len(digest) != 64 for digest in pack.asset_digests_sha256):
        issues.append("asset digests must be SHA-256 hex strings")
    expected = ScenarioPack.create(
        scenario_id=pack.scenario_id,
        task_revision=pack.task_revision,
        asset_digests_sha256=list(pack.asset_digests_sha256),
        initial_condition_digest_sha256=pack.initial_condition_digest_sha256,
        success_criterion_version=pack.success_criterion_version,
    ).pack_digest_sha256
    if expected != pack.pack_digest_sha256:
        issues.append("pack_digest_sha256 does not match content")
    return issues
