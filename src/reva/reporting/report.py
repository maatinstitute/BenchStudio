from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def build_evaluation_report(
    *,
    title: str,
    campaign: dict[str, Any],
    outcomes: dict[str, Any],
    diagnostics: dict[str, Any],
    claim_decisions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "schema": "reva_evaluation_report_v1",
        "title": title,
        "campaign": campaign,
        "outcomes": outcomes,
        "diagnostics": diagnostics,
        "claim_decisions": claim_decisions or [],
    }


def build_audited_evaluation_report(
    *,
    title: str,
    audit: Any,
    outcomes: dict[str, Any],
    diagnostics: dict[str, Any],
    paired_statistics: Any | None = None,
    acceptance: Any | None = None,
) -> dict[str, Any]:
    """Build the canonical report shape from an audited campaign result."""
    outcome_payload = dict(outcomes)
    if audit.outcome_provenance is not None:
        outcome_payload["provenance"] = audit.outcome_provenance.to_dict()
    if paired_statistics is not None:
        outcome_payload["paired_statistics"] = paired_statistics.to_dict()
    report = build_evaluation_report(
        title=title,
        campaign=audit.to_dict(),
        outcomes=outcome_payload,
        diagnostics=diagnostics,
        claim_decisions=[audit.claim.to_dict()],
    )
    if acceptance is not None:
        report["acceptance"] = acceptance.to_dict()
    return report


def render_html_report(report: dict[str, Any]) -> str:
    title = html.escape(str(report.get("title", "REVA evaluation")))
    payload = html.escape(json.dumps(report, indent=2, sort_keys=True))
    return (
        "<!doctype html>\n<html><head><meta charset='utf-8'>"
        f"<title>{title}</title>"
        "<style>body{font:15px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}"
        "pre{background:#f4f4f4;padding:1rem;overflow:auto}h1{color:#193b5c}</style>"
        f"</head><body><h1>{title}</h1><pre>{payload}</pre></body></html>\n"
    )


def write_html_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html_report(report), encoding="utf-8")
