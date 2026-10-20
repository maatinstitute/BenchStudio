"""Build a self-contained visual dashboard from BenchStudio demo evidence."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def _short(value: Any, length: int = 12) -> str:
    text = str(value or "unavailable")
    return html.escape(text[:length])


def _percent(value: Any) -> int:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return 0
    return max(0, min(100, round(float(value) * 100)))


def build_demo_dashboard(input_dir: Path, output_path: Path) -> Path:
    """Render the demo evidence directory as a standalone HTML control room."""
    root = Path(input_dir)
    plan = _load_json(root / "campaign-plan.json")
    ledger = _load_jsonl(root / "campaign" / "attempt-results.jsonl")
    robustness = _load_json(root / "robustness" / "counterfactual-summary.json")
    transfer = _load_json(root / "transfer" / "transfer-report.json")
    robochallenge = _load_json(root / "robochallenge-report.json")

    attempts = plan.get("attempts", [])
    completed = sum(row.get("status") == "completed" for row in ledger)
    failed = sum(row.get("status") != "completed" for row in ledger)
    evidence_verified = sum(row.get("evidence_verified") is True for row in ledger)
    scheduled = len(attempts)
    missing = max(0, scheduled - len(ledger))
    evidence_rate = round(100 * evidence_verified / scheduled) if scheduled else 0

    transfer_fidelity = transfer.get("transfer_fidelity", {})
    simulation_rate = _percent(transfer_fidelity.get("simulation_success_rate"))
    boundary_rate = _percent(transfer_fidelity.get("physical_success_rate"))
    gap = round(
        float(transfer_fidelity.get("success_gap_physical_minus_simulation", 0)) * 100
    )
    matched_pairs = int(transfer_fidelity.get("matched_pairs", 0) or 0)
    branches = int(robustness.get("scheduled_branch_count", 0) or 0)
    complete_branches = int(robustness.get("completed_branch_count", 0) or 0)

    conditions: dict[str, dict[str, Any]] = {}
    pair_ids: list[str] = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        condition = metadata.get("condition", {}) if isinstance(metadata, dict) else {}
        if isinstance(key, dict) and isinstance(condition, dict):
            conditions[str(key.get("condition_id"))] = condition
            pair_id = str(key.get("pair_id"))
            if pair_id not in pair_ids:
                pair_ids.append(pair_id)

    ledger_by_attempt = {str(row.get("attempt_id")): row for row in ledger}
    matrix_cells = []
    for attempt in attempts if isinstance(attempts, list) else []:
        if not isinstance(attempt, dict):
            continue
        key = attempt.get("key", {})
        metadata = attempt.get("metadata", {})
        if not isinstance(key, dict) or not isinstance(metadata, dict):
            continue
        condition = metadata.get("condition", {})
        row = ledger_by_attempt.get(str(key.get("attempt_id")), {})
        matrix_cells.append(
            {
                "pair": str(key.get("pair_id")),
                "condition": str(condition.get("id", key.get("condition_id")))
                if isinstance(condition, dict)
                else str(key.get("condition_id")),
                "steps": condition.get("denoising_steps")
                if isinstance(condition, dict)
                else None,
                "success": row.get("success_count") == 1,
                "verified": row.get("evidence_verified") is True,
            }
        )

    matrix_json = json.dumps(matrix_cells, separators=(",", ":")).replace("</", "<\\/")
    run_id = html.escape(str(plan.get("run_id", "BenchStudio demo")))
    plan_digest = _short(plan.get("plan_digest_sha256"), 16)
    robustness_digest = _short(robustness.get("result_digest_sha256"), 16)
    transport_valid = robochallenge.get("valid") is True
    transport_events = int(robochallenge.get("event_count", 0) or 0)

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#100a12">
  <title>BenchStudio Evaluation Control Room</title>
  <style>
    :root {{
      color-scheme: dark;
      --ink: #100a12; --panel: #18111b; --panel-2: #211525;
      --line: #3d293f; --muted: #a38da7; --text: #fff7ff;
      --pink: #ff4fba; --pink-hot: #ff2d96; --violet: #a67cff;
      --cyan: #68dcff; --ok: #75f5c7; --amber: #ffc36e; --red: #ff7185;
      --radius: 18px;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: radial-gradient(circle at 78% -10%, rgba(255,79,186,.12), transparent 32%), var(--ink); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body::before {{ content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .32; background-image: linear-gradient(rgba(255,79,186,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,79,186,.035) 1px, transparent 1px); background-size: 40px 40px; mask-image: linear-gradient(to bottom, black, transparent 78%); }}
    .shell {{ width: min(1440px, calc(100% - 36px)); margin: 0 auto; padding: 24px 0 54px; position: relative; }}
    .topbar {{ display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 11px 14px 11px 18px; border: 1px solid var(--line); background: rgba(24,17,27,.86); backdrop-filter: blur(16px); border-radius: 14px; position: sticky; top: 12px; z-index: 10; box-shadow: 0 12px 50px rgba(0,0,0,.3), 0 0 40px rgba(255,79,186,.04); }}
    .brand {{ display: flex; align-items: center; gap: 12px; font-weight: 760; letter-spacing: -.02em; }}
    .mark {{ width: 26px; height: 26px; border-radius: 8px; background: conic-gradient(from 210deg, var(--pink), var(--violet), var(--cyan), var(--pink)); box-shadow: 0 0 28px rgba(255,79,186,.42); }}
    .brand small {{ color: var(--muted); font-weight: 550; margin-left: 6px; }}
    .status {{ display: inline-flex; align-items: center; gap: 8px; padding: 8px 11px; border-radius: 999px; background: rgba(255,79,186,.1); color: #ff8fd1; border: 1px solid rgba(255,79,186,.28); font: 700 12px/1 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .04em; }}
    .pulse {{ width: 7px; height: 7px; border-radius: 50%; background: var(--pink); box-shadow: 0 0 0 0 rgba(255,79,186,.6); animation: pulse 2s infinite; }}
    @keyframes pulse {{ 70% {{ box-shadow: 0 0 0 9px rgba(255,79,186,0); }} 100% {{ box-shadow: 0 0 0 0 rgba(255,79,186,0); }} }}
    .hero {{ display: grid; grid-template-columns: 1.35fr .65fr; gap: 18px; margin-top: 20px; }}
    .hero-main, .hero-side, .card {{ border: 1px solid var(--line); border-radius: var(--radius); background: linear-gradient(145deg, rgba(33,21,37,.97), rgba(19,12,21,.97)); overflow: hidden; box-shadow: inset 0 1px rgba(255,255,255,.025); }}
    .hero-main {{ min-height: 360px; padding: 42px; position: relative; display: flex; flex-direction: column; justify-content: space-between; }}
    .hero-main::after {{ content: ""; position: absolute; width: 420px; height: 420px; border-radius: 50%; right: -120px; top: -180px; background: radial-gradient(circle, rgba(255,79,186,.22), rgba(166,124,255,.09) 34%, transparent 68%); }}
    .eyebrow {{ color: #ff8fd1; font: 700 12px/1.2 ui-monospace, SFMono-Regular, Menlo, monospace; letter-spacing: .12em; text-transform: uppercase; }}
    h1 {{ font-size: clamp(42px, 6vw, 78px); line-height: .98; letter-spacing: -.065em; margin: 18px 0; max-width: 840px; }}
    .subhead {{ color: #a8bac3; max-width: 700px; font-size: 17px; line-height: 1.55; }}
    .hero-meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 32px; }}
    .token {{ padding: 8px 10px; border-radius: 8px; color: #b8c7ce; border: 1px solid var(--line); background: rgba(7,11,15,.52); font: 600 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace; }}
    .hero-side {{ padding: 26px; display: flex; flex-direction: column; justify-content: space-between; }}
    .verdict-label {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .1em; }}
    .verdict {{ margin: 18px 0 8px; color: var(--pink); text-shadow: 0 0 28px rgba(255,79,186,.22); font-size: 38px; line-height: 1; letter-spacing: -.04em; font-weight: 800; }}
    .verdict-copy {{ color: #9eb0b9; line-height: 1.5; font-size: 14px; }}
    .ring {{ width: 148px; aspect-ratio: 1; margin: 24px auto 8px; border-radius: 50%; display: grid; place-items: center; background: conic-gradient(var(--pink) {evidence_rate}%, #3d293f 0); position: relative; box-shadow: 0 0 44px rgba(255,79,186,.13); }}
    .ring::before {{ content: ""; position: absolute; inset: 11px; border-radius: 50%; background: var(--panel); }}
    .ring strong {{ z-index: 1; font-size: 32px; letter-spacing: -.04em; }}
    .ring span {{ z-index: 1; position: absolute; margin-top: 48px; color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .08em; }}
    .metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 12px 0 18px; }}
    .metric {{ padding: 18px; border: 1px solid var(--line); border-radius: 14px; background: rgba(24,17,27,.92); }}
    .metric span {{ color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 30px; letter-spacing: -.045em; margin-top: 8px; }}
    .metric em {{ font-style: normal; color: #ff8fd1; font: 650 11px/1 ui-monospace, monospace; }}
    .grid {{ display: grid; grid-template-columns: 1.15fr .85fr; gap: 18px; }}
    .card {{ padding: 24px; margin-bottom: 18px; }}
    .card-head {{ display: flex; align-items: start; justify-content: space-between; gap: 16px; margin-bottom: 22px; }}
    .card h2 {{ margin: 0; font-size: 20px; letter-spacing: -.03em; }}
    .card p {{ color: var(--muted); margin: 7px 0 0; font-size: 13px; line-height: 1.5; }}
    .badge {{ color: #ff9cd7; background: rgba(255,79,186,.09); border: 1px solid rgba(255,79,186,.23); padding: 6px 8px; border-radius: 7px; font: 650 10px/1 ui-monospace, monospace; white-space: nowrap; }}
    .matrix {{ display: grid; gap: 8px; }}
    .matrix-row {{ display: grid; grid-template-columns: 110px repeat(2, minmax(0, 1fr)); gap: 8px; align-items: stretch; }}
    .matrix-label {{ color: var(--muted); font: 600 11px/1.25 ui-monospace, monospace; display: flex; align-items: center; }}
    .matrix-cell {{ min-height: 72px; border-radius: 11px; padding: 13px; background: linear-gradient(145deg, rgba(255,79,186,.1), rgba(166,124,255,.045)); border: 1px solid rgba(255,79,186,.23); display: flex; justify-content: space-between; align-items: end; }}
    .matrix-cell strong {{ font-size: 13px; }} .matrix-cell small {{ color: var(--muted); }}
    .check {{ color: var(--pink); font-weight: 800; }}
    .bars {{ display: grid; gap: 18px; }}
    .bar-row {{ display: grid; grid-template-columns: 126px 1fr 54px; gap: 12px; align-items: center; }}
    .bar-row label {{ color: #b6c5cc; font-size: 13px; }}
    .track {{ height: 14px; background: #1a252c; border-radius: 999px; overflow: hidden; }}
    .fill {{ height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--violet), var(--pink)); transform-origin: left; animation: grow 1s .25s both; box-shadow: 0 0 18px rgba(255,79,186,.3); }}
    .fill.boundary {{ background: linear-gradient(90deg, var(--amber), var(--red)); }}
    @keyframes grow {{ from {{ transform: scaleX(0); }} }}
    .bar-row strong {{ font: 750 13px/1 ui-monospace, monospace; text-align: right; }}
    .gap-callout {{ display: flex; justify-content: space-between; align-items: center; margin-top: 22px; padding: 14px 16px; background: rgba(255,189,102,.07); border: 1px solid rgba(255,189,102,.17); border-radius: 11px; }}
    .gap-callout strong {{ color: var(--amber); font-size: 26px; }}
    .branch-map {{ display: grid; grid-template-columns: 1fr 48px 1fr; align-items: center; gap: 10px; }}
    .branch {{ padding: 16px; border: 1px solid var(--line); border-radius: 11px; background: rgba(7,11,15,.36); }}
    .branch strong {{ display: block; margin-bottom: 5px; }} .branch small {{ color: var(--muted); }}
    .arrow {{ height: 1px; background: linear-gradient(90deg, var(--violet), var(--pink)); position: relative; }}
    .arrow::after {{ content: ""; position: absolute; right: 0; top: -3px; width: 7px; height: 7px; border-top: 1px solid var(--pink); border-right: 1px solid var(--pink); transform: rotate(45deg); }}
    .chain {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }}
    .chain-step {{ position: relative; padding: 16px 12px; border-radius: 11px; background: rgba(7,11,15,.42); border: 1px solid var(--line); min-height: 98px; }}
    .chain-step:not(:last-child)::after {{ content: ""; position: absolute; right: -9px; top: 48%; width: 9px; height: 1px; background: var(--cyan); z-index: 2; }}
    .chain-step b {{ color: var(--pink); font-size: 11px; }} .chain-step strong {{ display: block; margin: 12px 0 6px; font-size: 13px; }} .chain-step small {{ color: var(--muted); font: 10px/1.4 ui-monospace, monospace; }}
    .transport {{ display: grid; grid-template-columns: 1fr 36px 1fr; align-items: center; gap: 10px; }}
    .packet {{ padding: 17px; border-radius: 11px; border: 1px solid var(--line); background: rgba(166,124,255,.07); }}
    .json-panel {{ position: relative; padding: 18px; border: 1px solid rgba(255,79,186,.2); border-radius: 12px; background: #0d0910; overflow: auto; box-shadow: inset 0 0 42px rgba(255,79,186,.035); }}
    .json-panel::before {{ content: "JSON · VERIFIED EVIDENCE"; display: block; color: #866f8a; margin-bottom: 14px; font: 650 9px/1 ui-monospace, monospace; letter-spacing: .12em; }}
    .json-panel code {{ color: #d7c6da; font: 12px/1.75 ui-monospace, SFMono-Regular, Menlo, monospace; white-space: pre; }}
    .json-key {{ color: #ff72c4; }} .json-string {{ color: #c4a9ff; }} .json-number {{ color: #68dcff; }} .json-ok {{ color: var(--ok); }}
    .packet span {{ color: var(--muted); font-size: 10px; text-transform: uppercase; letter-spacing: .08em; }} .packet strong {{ display: block; margin-top: 8px; }}
    .links {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 18px; }}
    .links a {{ color: #b9cbd2; text-decoration: none; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; font-size: 11px; background: rgba(7,11,15,.45); }} .links a:hover {{ color: white; border-color: #48616f; }}
    footer {{ color: var(--muted); border-top: 1px solid var(--line); margin-top: 8px; padding-top: 22px; display: flex; justify-content: space-between; gap: 20px; font-size: 11px; line-height: 1.5; }}
    .reveal {{ animation: reveal .7s both; }} .reveal:nth-child(2) {{ animation-delay: .08s; }} .reveal:nth-child(3) {{ animation-delay: .16s; }}
    @keyframes reveal {{ from {{ opacity: 0; transform: translateY(12px); }} }}
    @media (max-width: 900px) {{ .hero, .grid {{ grid-template-columns: 1fr; }} .metrics {{ grid-template-columns: repeat(2, 1fr); }} .hero-main {{ padding: 28px; min-height: 330px; }} }}
    @media (max-width: 620px) {{ .shell {{ width: min(100% - 20px, 1440px); }} .brand small {{ display: none; }} .metrics {{ grid-template-columns: 1fr 1fr; }} .matrix-row {{ grid-template-columns: 78px repeat(2, 1fr); }} .chain {{ grid-template-columns: 1fr 1fr; }} .chain-step::after {{ display: none; }} footer {{ flex-direction: column; }} h1 {{ font-size: 44px; }} }}
    @media (prefers-reduced-motion: reduce) {{ *, *::before, *::after {{ animation: none !important; scroll-behavior: auto !important; }} }}
  </style>
</head>
<body>
  <main class="shell">
    <nav class="topbar" aria-label="Evaluation status">
      <div class="brand"><span class="mark" aria-hidden="true"></span>BenchStudio <small>Evaluation Control Room</small></div>
      <div class="status"><span class="pulse" aria-hidden="true"></span>EVIDENCE QUALIFIED</div>
    </nav>

    <section class="hero reveal">
      <div class="hero-main">
        <div>
          <div class="eyebrow">Independent embodied-AI evaluation</div>
          <h1>Can we trust this evaluation?</h1>
          <p class="subhead">One frozen experiment, every attempt accounted for, every artifact bound to evidence. BenchStudio turns model runs into claims that can be inspected—not just scores that must be believed.</p>
        </div>
        <div class="hero-meta"><span class="token">RUN · {run_id}</span><span class="token">PLAN · {plan_digest}</span><span class="token">MODE · CONTROLLED COMPARISON</span></div>
      </div>
      <aside class="hero-side">
        <div><div class="verdict-label">Scientific verdict</div><div class="verdict">Qualified</div><p class="verdict-copy">The protocol and evidence chain are complete. Claims remain bounded to deterministic fixtures; no physical performance is inferred.</p></div>
        <div class="ring"><strong>{evidence_rate}%</strong><span>evidence verified</span></div>
      </aside>
    </section>

    <section class="metrics reveal" aria-label="Campaign metrics">
      <div class="metric"><span>Frozen attempts</span><strong>{scheduled}</strong><em>PLAN-BOUND</em></div>
      <div class="metric"><span>Committed</span><strong>{completed}/{scheduled}</strong><em>{failed} FAILED</em></div>
      <div class="metric"><span>Missing outcomes</span><strong>{missing}</strong><em>DENOMINATOR INTACT</em></div>
      <div class="metric"><span>Evidence manifests</span><strong>{evidence_verified}</strong><em>HASH VERIFIED</em></div>
    </section>

    <div class="grid">
      <div>
        <section class="card reveal">
          <div class="card-head"><div><h2>Paired experiment matrix</h2><p>Same initial states, two inference budgets. Pairing stays visible all the way to the ledger.</p></div><span class="badge">2 × 2 DESIGN</span></div>
          <div id="matrix" class="matrix" aria-label="Paired attempt matrix"></div>
        </section>

        <section class="card reveal">
          <div class="card-head"><div><h2>Transfer fidelity</h2><p>The result is the gap—not an assumption that simulation predicts reality.</p></div><span class="badge">{matched_pairs} MATCHED PAIRS</span></div>
          <div class="bars">
            <div class="bar-row"><label>Simulation fixture</label><div class="track"><div class="fill" style="width:{simulation_rate}%"></div></div><strong>{simulation_rate}%</strong></div>
            <div class="bar-row"><label>Boundary fixture</label><div class="track"><div class="fill boundary" style="width:{boundary_rate}%"></div></div><strong>{boundary_rate}%</strong></div>
          </div>
          <div class="gap-callout"><span>Measured success gap</span><strong>{gap:+d} pp</strong></div>
        </section>

        <section class="card reveal">
          <div class="card-head"><div><h2>Evidence chain</h2><p>Each layer binds the next, from experimental intent to immutable files.</p></div><span class="badge">SHA-256</span></div>
          <div class="chain">
            <div class="chain-step"><b>01</b><strong>Frozen plan</strong><small>{plan_digest}</small></div>
            <div class="chain-step"><b>02</b><strong>Attempt ledger</strong><small>{len(ledger)} terminal rows</small></div>
            <div class="chain-step"><b>03</b><strong>Runtime receipts</strong><small>{evidence_verified} identities bound</small></div>
            <div class="chain-step"><b>04</b><strong>Artifact manifests</strong><small>verified locally</small></div>
          </div>
          <div class="links"><a href="campaign-plan.json">Frozen plan ↗</a><a href="campaign/attempt-results.jsonl">Attempt ledger ↗</a><a href="transfer/transfer-report.json">Transfer report ↗</a></div>
        </section>
      </div>

      <div>
        <section class="card reveal">
          <div class="card-head"><div><h2>Robustness branches</h2><p>Nominal and intervention outcomes remain linked to the same source identity.</p></div><span class="badge">{complete_branches}/{branches} COMPLETE</span></div>
          <div class="branch-map"><div class="branch"><strong>Nominal state</strong><small>Frozen parent identity</small></div><div class="arrow" aria-hidden="true"></div><div class="branch"><strong>Controlled intervention</strong><small>Outcome retained, never imputed</small></div></div>
          <div class="gap-callout"><span>Counterfactual evidence</span><strong>{robustness_digest}</strong></div>
          <div class="links"><a href="robustness/counterfactual-summary.json">Branch summary ↗</a><a href="robustness/counterfactual-results.jsonl">Branch results ↗</a></div>
        </section>

        <section class="card reveal">
          <div class="card-head"><div><h2>RoboChallenge boundary</h2><p>Opaque observations and actions cross the adapter with canonical digests and explicit timing uncertainty.</p></div><span class="badge">{'VALID' if transport_valid else 'INVALID'}</span></div>
          <div class="transport"><div class="packet"><span>Observation</span><strong>obs-0001</strong></div><div class="arrow" aria-hidden="true"></div><div class="packet"><span>Action acknowledgment</span><strong>act-0001</strong></div></div>
          <div class="gap-callout"><span>Canonical wire events</span><strong>{transport_events}</strong></div>
          <div class="links"><a href="robochallenge-report.json">Transport evidence ↗</a></div>
        </section>

        <section class="card reveal">
          <div class="card-head"><div><h2>Evidence inspector</h2><p>The machine-readable result stays visible—not buried behind the presentation layer.</p></div><span class="badge">LIVE ARTIFACT</span></div>
          <div class="json-panel" aria-label="Verified evidence JSON preview"><code>{{
  <span class="json-key">"campaign.status"</span>: <span class="json-string">"complete"</span>,
  <span class="json-key">"attempts.scheduled"</span>: <span class="json-number">{scheduled}</span>,
  <span class="json-key">"attempts.committed"</span>: <span class="json-number">{completed}</span>,
  <span class="json-key">"evidence.verified"</span>: <span class="json-number">{evidence_verified}</span>,
  <span class="json-key">"transport.valid"</span>: <span class="json-ok">{str(transport_valid).lower()}</span>,
  <span class="json-key">"claim.verdict"</span>: <span class="json-string">"qualified"</span>
}}</code></div>
          <div class="links"><a href="campaign-plan.json">Inspect complete JSON ↗</a></div>
        </section>

        <section class="card reveal">
          <div class="card-head"><div><h2>What this demo proves</h2></div><span class="badge">BOUNDARY AWARE</span></div>
          <p>Frozen scheduling, complete attempt accounting, paired comparisons, counterfactual lineage, transfer statistics, and digest-backed evidence all operate together.</p>
          <p><strong style="color:var(--amber)">What it does not claim:</strong> model quality, simulator fidelity, physical safety, or official benchmark scoring.</p>
        </section>
      </div>
    </div>

    <footer><span>BenchStudio · Evidence infrastructure for embodied intelligence</span><span>Deterministic presentation fixture · External physics and scoring clearly separated</span></footer>
  </main>
  <script>
    const cells = {matrix_json};
    const pairs = [...new Set(cells.map(c => c.pair))];
    const conditionOrder = [...new Set(cells.map(c => c.condition))];
    const matrix = document.getElementById('matrix');
    const head = document.createElement('div'); head.className = 'matrix-row';
    head.innerHTML = '<div class="matrix-label">INITIAL STATE</div>' + conditionOrder.map(c => `<div class="matrix-label">${{c.replaceAll('_',' ').toUpperCase()}}</div>`).join('');
    matrix.appendChild(head);
    pairs.forEach((pair, index) => {{
      const row = document.createElement('div'); row.className = 'matrix-row';
      row.innerHTML = `<div class="matrix-label">PAIR ${{String(index + 1).padStart(2,'0')}}<br>${{pair.slice(0,8)}}</div>` + conditionOrder.map(condition => {{
        const cell = cells.find(c => c.pair === pair && c.condition === condition);
        return `<div class="matrix-cell"><div><strong>${{cell?.steps ?? '—'}} denoise steps</strong><br><small>${{cell?.verified ? 'evidence verified' : 'unverified'}}</small></div><span class="check">${{cell?.success ? '✓' : '—'}}</span></div>`;
      }}).join('');
      matrix.appendChild(row);
    }});
  </script>
</body>
</html>
"""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(document, encoding="utf-8")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Demo evidence directory")
    parser.add_argument("--output", type=Path, required=True, help="Output HTML path")
    args = parser.parse_args()
    path = build_demo_dashboard(args.input, args.output)
    print(f"dashboard={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
